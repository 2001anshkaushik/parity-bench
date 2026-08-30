#!/usr/bin/env python3
"""Frame-parity probe — Ansh's ruling 2026-08-27: runs BEFORE any Films leg
and BEFORE the LI streaming refactor. Everything downstream branches on it.

Pre-registered rule (recorded here so the probe cannot be read as neutral
instrumentation; the probe itself only reports facts):
  A==B exactly on all three films -> frames/s stays primary, gate 3
    unchanged, same-frames precondition becomes a corpus-wide hash.
  Divergence -> realtime factor becomes the cross-arm headline, gate 3 goes
    per-film with CANNOT COMPARE, strict claims confined to films measured
    exact.

Three DECODE-ONLY cells per film. No containers started, no LI service, no
legs. One film per invocation.

  A  the ENGINE's exact invocation, run via `docker exec` against the
     already-running rr container's bundled imageio-ffmpeg, FILE input (the
     engine spools AVI and MP4 to a cache file and decodes from it at END —
     reader.py:418-437, :159-192, :232-240). The argv is assembled in
     engine_argv() from the engine source, cited line by line, and recorded
     verbatim in the artifact; the in-container sha256 of frame.py/reader.py
     binds the derivation to the source that actually runs.
  B  the LI service's exact invocation (li_video/pipeline.py:150-152):
     imageio-ffmpeg resolved in THIS interpreter's env (the floor venv),
     `-i pipe:0`, stdin fed by streaming 1 MiB reads. Stated deviation: the
     service holds the whole blob and passes it via subprocess.run(input=);
     this probe streams the feed — pipe-read granularity is invisible to
     ffmpeg's demuxer and cannot change frame selection, and holding a whole
     film would reproduce the bug this probe exists to measure.
  C  the LI argv with the film PATH instead of pipe:0 — isolates input
     topology (seekable file vs stream) from every other argv difference.

Fail-closed: a nonzero ffmpeg exit is a recorded FAILURE for that cell — a
shorter frame list is never silently accepted. (The engine itself fails OPEN
here: reader.py:344 discards the cached-path exit status; this probe must
not copy that.) Cell B dying with 'moov atom not found' is an
EXPECTED-CLASS result — a non-seekable MP4 with a trailing moov cannot be
demuxed from a pipe — recorded as such, because it is one of the questions.

Splitting: cell A mirrors the engine's IEND chunk-walk
(ai/common/avi/frame.py:116-163 + buffer trim :165-182); cells B/C mirror
pipeline.py's signature scan (:154-163) INCLUDING its behaviour of keeping a
truncated trailing PNG. BOTH parsers run on every cell's stream and any
disagreement between them is reported (`--self-test` proves the agreement
case, the known truncated-tail disagreement, and the flip machinery, with no
ffmpeg or docker needed).

Null control: --null-flip XORs one byte of the first frame of cell A (or the
first requested cell) before hashing, in both parsers; every comparison
involving that cell MUST then report a mismatch or the probe exits 3.

Memory discipline: frames are hashed from the stream — never written to
disk, never accumulated; each parser's peak buffer is recorded and bounded
(a cell whose parser buffer exceeds the bound is FAILED, not ballooned).

Artifact binds: film sha256 (+ optional --film-sha-expected refusal), the
three ffmpeg binaries' sha256 and -version strings, the rr image id, the
in-container engine source hashes, and this repo's git HEAD.

Exit codes: 0 = probe completed and wrote the artifact (DIVERGENCE and
expected-class cell failures are RESULTS, not errors); 1 = machinery or
guard failure; 3 = null control failed to fire; 4 = --self-test failure.

Run (box; the host has no ffmpeg — PYBIN must be the floor venv):
  ~/.venv-floor/bin/python3 working/video/probe/probe_frame_parity.py \
      --film ~/films_probe/flight_to_nowhere.mp4 \
      --film-sha-expected <sha256 from corpus_manifest.json>
"""

import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
import threading
import time
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # working/video
from argtypes import positive_int  # noqa: E402 — register entry 8

PNG_SIG = b'\x89PNG\r\n\x1a\n'          # pipeline.py:49 == frame.py:15 (SOI)
INTERVAL_S = 15                          # benchmark_video_detect.pipe:29 and
                                         # li_video/service.py:34 (WS1V_INTERVAL_S
                                         # default) — the settled interval.
PARSER_BUFFER_BOUND = 512 * 1024 * 1024  # fail the cell before the probe OOMs
UTC = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())


# --------------------------------------------------------------------- argv

def engine_argv(ffexec: str, video_path: str) -> list:
    """The engine's exact ffmpeg invocation for the measured pipe's config.

    reader.py:232-240: ffargs = [ffexec] + input + self._args, where the
    cached path (AVI and MP4 are both classified not-stdin-compatible,
    reader.py:159-192) uses input = ['-i', <cache file>] (:236-237).
    frame.py:56-112 builds self._args for the interval profile with the
    measured pipe's values (benchmark_video_detect.pipe:27-32: interval 15,
    start_time 0, duration 0, no scale keys; per-key override semantics
    engine/ai/common/config.py:91-94 — the pipe's literals win):
      - '-ss {start_time}' first (frame.py:56-59); start_time 0 -> '-ss 0'
        (at zero, '0' vs '0.0' cannot affect selection; recorded verbatim)
      - fps = 1.0/15 (frame_grabber/IGlobal.py:46); fps < 1 ->
        f'fps=1/{round(1/fps)}' = 'fps=1/15' (frame.py:50-53)
      - filters ['fps=1/15'] + 'showinfo' always appended (frame.py:77-83);
        no scale filter (scale_width/height default -1/-1, frame.py:65-69)
      - no '-frames:v' (max_frames None, frame.py:92-94); no '-t'
        (duration 0 is falsy, frame.py:97-98)
      - trailing '-hide_banner -loglevel info' AFTER the '-' output target,
        exactly as frame.py:101-112 orders them (ffmpeg warns 'Trailing
        option(s) found' and ignores them; fidelity over tidiness).
    """
    return [ffexec, '-i', video_path,
            '-ss', '0',
            '-vf', 'fps=1/15,showinfo',
            '-f', 'image2pipe',
            '-fps_mode', 'passthrough',
            '-vcodec', 'png',
            '-',
            '-hide_banner', '-loglevel', 'info']


def li_argv(ffexec: str, input_arg: str) -> list:
    """li_video/pipeline.py:150-152 verbatim, interval 15:
    input_arg is 'pipe:0' (cell B, the service's shape) or the film path
    (cell C, the topology discriminator)."""
    return [ffexec, '-nostdin', '-loglevel', 'error', '-i', input_arg,
            '-vf', f'fps=1/{INTERVAL_S}', '-f', 'image2pipe',
            '-fps_mode', 'passthrough', '-vcodec', 'png', '-']


# ------------------------------------------------------------------ parsers

class IendWalk:
    """Mirror of the engine's splitter: frame.py:116-163 extract_complete_png
    (find SIG, walk length+type+data+crc chunks to IEND) driven as
    frame.py:165-182 _processBuffer drives it (emit, then trim the buffer
    past the emitted PNG). A trailing incomplete PNG is DROPPED, as the
    engine drops it; bytes before the SIG are discarded by the trim, counted
    here as discarded_prefix_bytes."""

    name = 'iend_walk (engine frame.py:116-182)'

    def __init__(self):
        self.buf = bytearray()
        self.max_buffer = 0
        self.discarded_prefix_bytes = 0
        self.dropped_tail_bytes = 0

    def _extract_one(self):
        data = self.buf
        pos = data.find(PNG_SIG)
        if pos == -1:
            return None
        i = pos + len(PNG_SIG)
        while i + 8 <= len(data):
            length = int.from_bytes(data[i:i + 4], 'big')
            ctype = bytes(data[i + 4:i + 8])
            nxt = i + 4 + 4 + length + 4
            if nxt > len(data):
                return None
            i = nxt
            if ctype == b'IEND':
                return bytes(data[pos:i]), pos, i
        return None

    def feed(self, chunk: bytes):
        self.buf.extend(chunk)
        self.max_buffer = max(self.max_buffer, len(self.buf))
        out = []
        while True:
            got = self._extract_one()
            if got is None:
                return out
            png, pos, end = got
            self.discarded_prefix_bytes += pos
            out.append(png)
            self.buf = self.buf[end:]

    def finish(self):
        self.dropped_tail_bytes = len(self.buf)   # engine: incomplete -> dropped
        return []


class SigScan:
    """Mirror of the LI service's splitter: pipeline.py:154-163 — cut at each
    next PNG signature, keep only segments that START with the signature,
    and (faithfully) keep a truncated trailing PNG at EOF. Segments not
    starting with the signature are counted, not emitted."""

    name = 'sig_scan (li pipeline.py:154-163)'

    def __init__(self):
        self.buf = bytearray()
        self.max_buffer = 0
        self.dropped_nonsig_bytes = 0
        self.dropped_tail_bytes = 0

    def feed(self, chunk: bytes):
        self.buf.extend(chunk)
        self.max_buffer = max(self.max_buffer, len(self.buf))
        out = []
        while True:
            j = self.buf.find(PNG_SIG, 1)
            if j == -1:
                return out
            seg = bytes(self.buf[:j])
            if seg.startswith(PNG_SIG):
                out.append(seg)
            else:
                self.dropped_nonsig_bytes += len(seg)
            self.buf = self.buf[j:]

    def finish(self):
        if not self.buf:
            return []
        seg = bytes(self.buf)
        self.buf = bytearray()
        if seg.startswith(PNG_SIG):
            return [seg]                 # pipeline keeps the truncated tail
        self.dropped_nonsig_bytes += len(seg)
        return []


# ------------------------------------------------------------------- helpers

def sha256_file(path: Path, chunk: int = 1 << 20) -> tuple:
    h, n = hashlib.sha256(), 0
    with open(path, 'rb') as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
            n += len(b)
    return h.hexdigest(), n


def run_text(argv, timeout=60):
    p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def preserve(path: Path):
    """Entry 7: the quotable command must not destroy prior evidence."""
    if path.exists():
        aside = Path(f'{path}.prev_{UTC}')
        path.rename(aside)
        print(f'note: existing {path.name} moved aside as {aside.name}')


class RssMonitor:
    """Poll VmHWM ~2 Hz. Host cells read /proc/<pid>/status directly;
    cell A locates the in-container ffmpeg via pgrep on the filter string
    and reads its /proc through docker exec. Peak-by-polling is the recorded
    basis — a spike between polls can be missed; ffmpeg decode RSS is flat."""

    def __init__(self, container=None, pattern=None, pid=None):
        self.container, self.pattern, self.pid = container, pattern, pid
        self.peak_kb, self.samples = None, 0
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _read_status(self):
        try:
            if self.container:
                if self.pid is None:
                    rc, out, _ = run_text(['docker', 'exec', self.container,
                                           'sh', '-c',
                                           f"pgrep -f '{self.pattern}' | head -1"],
                                          timeout=10)
                    if rc != 0 or not out:
                        return None
                    self.pid = int(out.split()[0])
                rc, out, _ = run_text(['docker', 'exec', self.container, 'cat',
                                       f'/proc/{self.pid}/status'], timeout=10)
                if rc != 0:
                    return None
                txt = out
            else:
                txt = Path(f'/proc/{self.pid}/status').read_text()
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return None
        m = re.search(r'VmHWM:\s*(\d+)\s*kB', txt)
        return int(m.group(1)) if m else None

    def _run(self):
        while not self._stop.is_set():
            v = self._read_status()
            if v is not None:
                self.peak_kb = v
                self.samples += 1
            self._stop.wait(0.5)

    def stop(self):
        self._stop.set()
        self.thread.join(timeout=5)

    @property
    def basis(self):
        where = 'in-container /proc via docker exec' if self.container else 'host /proc'
        return (f'VmHWM polled ~2 Hz from {where}; {self.samples} sample(s); '
                'a peak between polls can be missed')


def compare_lists(na, ha, nb, hb):
    first = next((i for i, (x, y) in enumerate(zip(ha, hb)) if x != y), None)
    if first is None and na != nb:
        first = min(na, nb)
    return {'equal_counts': na == nb, 'equal_hashes': (na == nb and first is None),
            'n_a': na, 'n_b': nb, 'first_mismatch_index': first}


# ---------------------------------------------------------------- cell runner

def run_cell(name, argv, *, feeder_path=None, rss: RssMonitor, flip_frame0,
             read_chunk, timeout_s, stderr_tail_cap=16384):
    canonical = IendWalk() if name == 'A' else SigScan()
    crosscheck = SigScan() if name == 'A' else IendWalk()
    can_shas, cc_shas = [], []
    stderr_tail = bytearray()
    stderr_bytes = [0]
    feeder_note = [None]
    timed_out = [False]

    proc = subprocess.Popen(argv, stdin=(subprocess.PIPE if feeder_path else
                                         subprocess.DEVNULL),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    rss.pid = rss.pid if rss.container else proc.pid
    rss.thread.start()

    def _feed():
        fed = 0
        try:
            with open(feeder_path, 'rb') as fh:
                while True:
                    b = fh.read(read_chunk)
                    if not b:
                        break
                    proc.stdin.write(b)
                    fed += len(b)
            proc.stdin.close()
        except (BrokenPipeError, OSError) as exc:
            feeder_note[0] = f'feed stopped at {fed} bytes: {exc!r}'
            try:
                proc.stdin.close()
            except OSError:
                pass

    def _drain_stderr():
        while True:
            b = proc.stderr.read(65536)
            if not b:
                return
            stderr_bytes[0] += len(b)
            stderr_tail.extend(b)
            del stderr_tail[:-stderr_tail_cap]

    threads = [threading.Thread(target=_drain_stderr, daemon=True)]
    if feeder_path:
        threads.append(threading.Thread(target=_feed, daemon=True))
    for t in threads:
        t.start()

    killer = threading.Timer(timeout_s, lambda: (timed_out.__setitem__(0, True),
                                                 proc.kill()))
    killer.start()
    t0 = time.monotonic()
    overflow = None
    try:
        while True:
            b = proc.stdout.read(read_chunk)
            if not b:
                break
            for parser, shas in ((canonical, can_shas), (crosscheck, cc_shas)):
                for frame in parser.feed(b):
                    if flip_frame0 and not shas:
                        f = bytearray(frame)
                        f[len(f) // 2] ^= 0xFF
                        frame = bytes(f)
                    shas.append(hashlib.sha256(frame).hexdigest())
                if parser.max_buffer > PARSER_BUFFER_BOUND:
                    overflow = (f'{parser.name} buffer {parser.max_buffer} B '
                                f'exceeded bound {PARSER_BUFFER_BOUND} B')
                    proc.kill()
            if overflow:
                break
        for parser, shas in ((canonical, can_shas), (crosscheck, cc_shas)):
            for frame in parser.finish():
                if flip_frame0 and not shas:
                    f = bytearray(frame)
                    f[len(f) // 2] ^= 0xFF
                    frame = bytes(f)
                shas.append(hashlib.sha256(frame).hexdigest())
        rc = proc.wait()
    finally:
        killer.cancel()
        rss.stop()
        for t in threads:
            t.join(timeout=10)
    wall = round(time.monotonic() - t0, 2)

    tail = stderr_tail.decode('utf-8', 'replace')
    if overflow:
        status = f'FAILED — {overflow}'
    elif timed_out[0]:
        status = f'FAILED — timeout after {timeout_s}s (ffmpeg killed)'
    elif rc == 0:
        status = 'OK'
    elif feeder_path and 'moov atom not found' in tail:
        status = ('FAILED-EXPECTED-CLASS — moov atom not found on pipe input '
                  '(non-seekable MP4 with trailing moov; one of the questions)')
    else:
        status = f'FAILED — ffmpeg rc={rc}'

    cross = compare_lists(len(can_shas), can_shas, len(cc_shas), cc_shas)
    return {
        'argv': argv, 'status': status, 'rc': rc, 'wall_s': wall,
        'peak_rss_kb': rss.peak_kb, 'peak_rss_basis': rss.basis,
        'n_frames': len(can_shas), 'frame_sha256': can_shas,
        'parser': canonical.name,
        'parser_max_buffer_bytes': canonical.max_buffer,
        'parser_dropped': {'prefix': getattr(canonical, 'discarded_prefix_bytes', 0),
                           'nonsig': getattr(canonical, 'dropped_nonsig_bytes', 0),
                           'tail': canonical.dropped_tail_bytes},
        'crosscheck': {'parser': crosscheck.name, 'n_frames': len(cc_shas),
                       'agree': cross['equal_hashes'],
                       'first_disagreement_index': cross['first_mismatch_index'],
                       'dropped_tail_bytes': crosscheck.dropped_tail_bytes},
        'stderr_bytes': stderr_bytes[0], 'stderr_tail': tail[-4096:],
        'feeder_note': feeder_note[0],
        'null_flip_applied': bool(flip_frame0),
    }


# ------------------------------------------------------------ container side

def container_ffmpeg(container, engine_pythons):
    """Resolve the engine's ffmpeg exactly as the engine does
    (reader.py:5,229: imageio_ffmpeg.get_ffmpeg_exe()), via a python inside
    the engine's env; fall back to a filesystem find that must be
    unambiguous. Fail closed rather than guess."""
    for py in engine_pythons:
        rc, out, _ = run_text(['docker', 'exec', container, py, '-c',
                               'import imageio_ffmpeg; '
                               'print(imageio_ffmpeg.get_ffmpeg_exe())'])
        if rc == 0 and out:
            return out.splitlines()[-1].strip(), f'{py} get_ffmpeg_exe()'
    rc, out, _ = run_text(['docker', 'exec', container, 'sh', '-c',
                           "find /opt/rocketride -type f -path '*imageio_ffmpeg*' "
                           "-name 'ffmpeg*' 2>/dev/null"])
    hits = [l for l in out.splitlines() if l.strip()] if rc == 0 else []
    if len(hits) == 1:
        return hits[0].strip(), 'find (single imageio_ffmpeg binary in /opt/rocketride)'
    raise SystemExit(
        f'NOT DONE — cannot resolve the engine ffmpeg in container {container!r}: '
        f'tried pythons {engine_pythons}, find gave {len(hits)} hit(s) {hits[:3]}. '
        'Pass --engine-python <path-to-python-inside-container> that can '
        '`import imageio_ffmpeg`.')


def container_facts(container, ff):
    facts = {}
    rc, out, _ = run_text(['docker', 'inspect', '--format', '{{.Image}}', container])
    if rc != 0:
        raise SystemExit(f'NOT DONE — docker inspect {container!r} failed (rc={rc}); '
                         'is the rr container up? This probe never starts one.')
    facts['rr_image_id'] = out
    rc, out, _ = run_text(['docker', 'exec', container, 'sh', '-c',
                           f'sha256sum "{ff}" 2>/dev/null'])
    facts['ffmpeg_sha256'] = out.split()[0] if rc == 0 and out else f'UNAVAILABLE rc={rc}'
    rc, out, err = run_text(['docker', 'exec', container, ff, '-version'])
    facts['ffmpeg_version'] = (out or err).splitlines()[0] if (out or err) else 'UNAVAILABLE'
    for rel in ('ai/common/avi/frame.py', 'ai/common/avi/reader.py'):
        rc, out, _ = run_text(['docker', 'exec', container, 'sh', '-c',
                               f'sha256sum /opt/rocketride/engine/{rel} 2>/dev/null'])
        facts[f'engine_{Path(rel).name}_sha256'] = \
            out.split()[0] if rc == 0 and out else f'UNAVAILABLE rc={rc}'
    return facts


# ------------------------------------------------------------------ selftest

def _mk_png(payload: bytes) -> bytes:
    def chunk(ctype, data):
        return (struct.pack('>I', len(data)) + ctype + data
                + struct.pack('>I', zlib.crc32(ctype + data) & 0xFFFFFFFF))
    ihdr = struct.pack('>IIBBBBB', 2, 2, 8, 0, 0, 0, 0)
    return (PNG_SIG + chunk(b'IHDR', ihdr) + chunk(b'IDAT', payload)
            + chunk(b'IEND', b''))


def self_test() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f'  {"PASS" if cond else "FAIL"}  {name}')
        ok = ok and cond

    pngs = [_mk_png(bytes([i]) * (7 + i)) for i in range(3)]
    stream = b''.join(pngs)

    def drive(parser, data, step):
        frames = []
        for i in range(0, len(data), step):
            frames += parser.feed(data[i:i + step])
        frames += parser.finish()
        return frames

    a = drive(IendWalk(), stream, 7)
    b = drive(SigScan(), stream, 7)
    check('both parsers: 3 frames from 7-byte feeds', len(a) == 3 and len(b) == 3)
    check('both parsers: identical byte spans', a == b == pngs)

    trunc = stream[:-5]
    a2 = drive(IendWalk(), trunc, 11)
    b2 = drive(SigScan(), trunc, 11)
    check('truncated tail: IEND walk drops it (2 frames)', len(a2) == 2)
    check('truncated tail: SIG scan keeps it (3 frames, mirror of pipeline)',
          len(b2) == 3)
    cross = compare_lists(len(a2), [hashlib.sha256(x).hexdigest() for x in a2],
                          len(b2), [hashlib.sha256(x).hexdigest() for x in b2])
    check('disagreement reporter fires on the truncated stream',
          not cross['equal_hashes'] and cross['first_mismatch_index'] == 2)

    ha = [hashlib.sha256(x).hexdigest() for x in a]
    flipped = bytearray(a[0])
    flipped[len(flipped) // 2] ^= 0xFF
    hf = [hashlib.sha256(bytes(flipped)).hexdigest()] + ha[1:]
    c = compare_lists(3, ha, 3, hf)
    check('null-flip machinery: comparator reports the mismatch at index 0',
          not c['equal_hashes'] and c['first_mismatch_index'] == 0)

    p = IendWalk()
    drive(p, stream, 7)
    check('parser buffer stayed bounded (< one frame + one feed)',
          p.max_buffer <= max(len(x) for x in pngs) + 7)

    bad = _mk_png(b'x')[:-1] + b'\x00'          # corrupt IEND crc byte
    check('IEND walk needs types+lengths only (crc not verified, as engine)',
          len(drive(IendWalk(), bad, 5)) == 1)

    # ENTRY 27 (2026-08-30 sweep kill — a missing `import re` passed
    # py_compile AND a green self-test): every probe self-test scans the
    # video tree for unresolvable names. Lazy import: live paths untouched.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # working/
    from harness.static_names import probe_selftest_findings
    sn = probe_selftest_findings(__file__)
    check('static names: every video-tree name resolves (entry 27)', sn == {})
    if sn:
        print('  UNRESOLVED:', sn)

    print('self-test:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 4


# ----------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--film', help='path to one film (one film per invocation)')
    ap.add_argument('--film-sha-expected', default=None,
                    help='sha256 from corpus_manifest.json; mismatch refuses the run')
    ap.add_argument('--cells', default='ABC',
                    help="subset of 'ABC' (A=engine exec, B=LI pipe, C=LI file)")
    ap.add_argument('--container', default='rr')
    ap.add_argument('--engine-python', action='append', default=None,
                    help='python inside the container that imports imageio_ffmpeg '
                         '(repeatable; tried in order before the find fallback)')
    ap.add_argument('--read-chunk-bytes', type=positive_int('read-chunk-bytes',
                                                            1 << 26),
                    default=1 << 20)
    ap.add_argument('--cell-timeout-s', type=positive_int('cell-timeout-s', 86400),
                    default=1800)
    ap.add_argument('--null-flip', action='store_true',
                    help='control: flip one byte of the first frame of the first '
                         'cell pre-hash; comparisons MUST mismatch or exit 3')
    ap.add_argument('--out', default=None)
    ap.add_argument('--self-test', action='store_true',
                    help='parser + comparator + flip machinery on synthetic PNGs; '
                         'no ffmpeg, no docker (runs on the laptop)')
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not args.film:
        ap.error('--film is required (unless --self-test)')
    cells = list(dict.fromkeys(c for c in args.cells.upper()))
    if not cells or any(c not in 'ABC' for c in cells):
        ap.error(f"--cells must be a subset of 'ABC', got {args.cells!r}")
    if args.film_sha_expected and not re.fullmatch(r'[0-9a-f]{64}',
                                                   args.film_sha_expected):
        ap.error('--film-sha-expected must be 64 lowercase hex chars')

    film = Path(args.film).expanduser().resolve()
    if not film.is_file():
        raise SystemExit(f'NOT DONE — film not found: {film}')

    need_floor = any(c in cells for c in 'BC')
    ff_local = None
    if need_floor:
        try:
            import imageio_ffmpeg
            ff_local = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            raise SystemExit(
                'NOT DONE — this interpreter cannot import imageio_ffmpeg and the '
                'host has no ffmpeg. Run under the floor venv: '
                '~/.venv-floor/bin/python3 (setup_floor_venv.sh); cells B/C '
                'resolve ffmpeg exactly as pipeline.py:107-108 does.')

    print(f'film sha256: hashing {film.name} ...')
    film_sha, film_bytes = sha256_file(film)
    if args.film_sha_expected and film_sha != args.film_sha_expected:
        raise SystemExit(f'NOT DONE — film sha mismatch for {film.name}: '
                         f'measured {film_sha}, expected {args.film_sha_expected}. '
                         'Refusing to measure an unverified input.')

    repo = Path(__file__).resolve().parents[3]
    rc, head, _ = run_text(['git', '-C', str(repo), 'rev-parse', 'HEAD'])
    git_head = head if rc == 0 else 'UNAVAILABLE'

    artifact = {
        'probe': 'frame_parity', 'created_utc': UTC, 'git_head': git_head,
        'film': {'path': str(film), 'name': film.name,
                 'bytes': film_bytes, 'sha256': film_sha,
                 'sha_expected': args.film_sha_expected},
        'interval_s': INTERVAL_S,
        'pre_registered_rule': 'see module docstring; the probe reports facts only',
        'cells': {}, 'comparisons': {},
    }

    flip_cell = cells[0] if args.null_flip else None
    if args.null_flip:
        artifact['null_flip'] = {'cell': flip_cell, 'frame_index': 0,
                                 'byte': 'mid-byte XOR 0xFF, both parsers, pre-hash'}

    in_container_path = None
    try:
        if 'A' in cells:
            pythons = args.engine_python or ['/opt/rocketride/engine/bin/python3',
                                             '/opt/rocketride/engine/bin/python']
            ff_engine, basis = container_ffmpeg(args.container, pythons)
            facts = container_facts(args.container, ff_engine)
            artifact['engine'] = dict(facts, ffmpeg_path=ff_engine,
                                      ffmpeg_resolved_by=basis,
                                      container=args.container)
            in_container_path = f'/tmp/parity_probe_{film.name}'
            rc, _, err = run_text(['docker', 'cp', str(film),
                                   f'{args.container}:{in_container_path}'],
                                  timeout=600)
            if rc != 0:
                raise SystemExit(f'NOT DONE — docker cp into {args.container} '
                                 f'failed: {err[-300:]}')
            rc, out, _ = run_text(['docker', 'exec', args.container, 'sh', '-c',
                                   f'stat -c %s "{in_container_path}"'])
            if rc != 0 or int(out) != film_bytes:
                raise SystemExit(f'NOT DONE — in-container copy size {out!r} != '
                                 f'{film_bytes}; refusing (read-back failed)')
            argv = ['docker', 'exec', args.container] \
                + engine_argv(ff_engine, in_container_path)
            print(f'cell A: {" ".join(argv)}')
            artifact['cells']['A'] = run_cell(
                'A', argv, rss=RssMonitor(container=args.container,
                                          # '[f]fmpeg' so the pgrep sh's own
                                          # cmdline cannot match its pattern
                                          pattern='[f]fmpeg.*showinfo'),
                flip_frame0=(flip_cell == 'A'),
                read_chunk=args.read_chunk_bytes, timeout_s=args.cell_timeout_s)
            artifact['cells']['A']['input_mode'] = \
                f'file (docker cp -> {in_container_path}; engine cache-file topology)'

        if need_floor:
            vsha, _ = sha256_file(Path(ff_local))
            _, vout, verr = run_text([ff_local, '-version'])
            local_bin = {'ffmpeg_path': ff_local, 'ffmpeg_sha256': vsha,
                         'ffmpeg_version': (vout or verr).splitlines()[0],
                         'resolved_by': 'imageio_ffmpeg.get_ffmpeg_exe() '
                                        '(pipeline.py:107-108) in this venv'}
            artifact['floor'] = dict(local_bin, python=sys.executable)
            if 'B' in cells:
                argv = li_argv(ff_local, 'pipe:0')
                print(f'cell B: {" ".join(argv)}  (stdin <- {film.name}, 1 MiB reads)')
                artifact['cells']['B'] = run_cell(
                    'B', argv, feeder_path=film, rss=RssMonitor(),
                    flip_frame0=(flip_cell == 'B'),
                    read_chunk=args.read_chunk_bytes,
                    timeout_s=args.cell_timeout_s)
                artifact['cells']['B']['input_mode'] = \
                    'pipe:0, stdin streamed in 1 MiB reads (stated deviation: the ' \
                    'service passes whole bytes; granularity cannot change selection)'
            if 'C' in cells:
                argv = li_argv(ff_local, str(film))
                print(f'cell C: {" ".join(argv)}')
                artifact['cells']['C'] = run_cell(
                    'C', argv, rss=RssMonitor(),
                    flip_frame0=(flip_cell == 'C'),
                    read_chunk=args.read_chunk_bytes,
                    timeout_s=args.cell_timeout_s)
                artifact['cells']['C']['input_mode'] = \
                    'file (LI argv with the path in place of pipe:0)'
    finally:
        if in_container_path:
            run_text(['docker', 'exec', args.container, 'rm', '-f',
                      in_container_path])

    for a, b in (('A', 'B'), ('A', 'C'), ('B', 'C')):
        if a not in artifact['cells'] or b not in artifact['cells']:
            continue
        ca, cb = artifact['cells'][a], artifact['cells'][b]
        failed = [n for n, c in ((a, ca), (b, cb)) if c['status'] != 'OK']
        if failed:
            artifact['comparisons'][f'{a}_vs_{b}'] = {
                'verdict': f'CANNOT COMPARE — cell(s) {failed} not OK '
                           '(a fault in the evidence, not a finding about the arms)'}
            continue
        cmp_ = compare_lists(ca['n_frames'], ca['frame_sha256'],
                             cb['n_frames'], cb['frame_sha256'])
        cmp_['verdict'] = ('EXACT' if cmp_['equal_hashes'] else
                           f"DIVERGENT — counts {cmp_['n_a']} vs {cmp_['n_b']}, "
                           f"first mismatch at {cmp_['first_mismatch_index']}")
        artifact['comparisons'][f'{a}_vs_{b}'] = cmp_

    out = Path(args.out) if args.out else \
        Path(__file__).parent / f'probe_frame_parity_{film.stem}.json'
    preserve(out)
    out.write_text(json.dumps(artifact, indent=1))
    readback = json.loads(out.read_text())        # entry 22: read back, then report
    glance = ' | '.join(
        [f"{n}: {c['status']} n={c['n_frames']}" for n, c in
         sorted(readback['cells'].items())]
        + [f"{k}: {v['verdict']}" for k, v in sorted(readback['comparisons'].items())])
    print(f'wrote {out}')
    print(f'AT A GLANCE — {readback["film"]["name"]}: {glance}')

    if args.null_flip:
        flips = [k for k, v in readback['comparisons'].items()
                 if flip_cell in k.split('_vs_')]
        fired = flips and all(
            v.get('equal_hashes') is False
            for k, v in readback['comparisons'].items() if k in flips)
        if not fired:
            print('NULL CONTROL FAILED TO FIRE — the comparator cannot fail; '
                  'fix before trusting any EXACT verdict')
            return 3
        print(f'null control fired: flipped frame in cell {flip_cell} reported '
              'as mismatch in every comparison involving it')
    return 0


if __name__ == '__main__':
    sys.exit(main())
