#!/usr/bin/env python3
"""The 2026-08-23 step-0 death, reproduced against the real code, plus every
verdict's null control. No box, no docker, no network — and a TRIPWIRE on the
network: fetch_url is replaced with a function that raises, so any verify that
reaches for a download fails this test rather than a campaign.

Run:  python3 working/video/test_corpus_locator_sites.py
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fetch_ami_video as fav          # noqa: E402
import corpus_locator as loc           # noqa: E402

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = '') -> None:
    if not cond:
        FAILS.append(name)
    print(f'  {"ok  " if cond else "FAIL"} {name}' + (f'\n       {detail}' if not cond else ''))


class NetworkTouched(AssertionError):
    pass


def tripwire(url, dest, timeout=120):
    raise NetworkTouched(f'fetch_url({url!r}, {dest.name}) was called')


def run(argv: list[str], fetch=tripwire) -> tuple[int, str]:
    fav.fetch_url = fetch
    buf = io.StringIO()
    sys.argv = ['fetch_ami_video.py', *argv]
    try:
        with redirect_stdout(buf):
            rc = fav.main()
    except NetworkTouched as e:
        return 99, buf.getvalue() + f'\nNETWORK TOUCHED: {e}'
    except SystemExit as e:
        rc = int(e.code) if isinstance(e.code, int) else 1
    return rc, buf.getvalue()


def make_corpus(d: Path, names, content=b'AVI-BYTES-') -> list[dict]:
    d.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, n in enumerate(names):
        blob = content + n.encode() * 50
        (d / n).write_bytes(blob)
        rows.append({'file': n, 'role': 'measured' if i < len(names) - 1 else 'warm',
                     'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest(),
                     'url': '', 'video_s': 100.0, 'expected_frames_measured': 7})
    return rows


def write_manifest(path: Path, rows, meta=None):
    meta = {'_meta': {'built_utc': '2026-08-23T00:00:00Z', **(meta or {})}}
    path.write_text(json.dumps(meta) + '\n' + ''.join(json.dumps(r) + '\n' for r in rows))


def data_lines(path: Path):
    return [l for l in path.read_text().splitlines() if l.strip() and '_meta' not in json.loads(l)]


def main() -> int:
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        full, video = d / 'corpus' / 'ami' / 'full', d / 'corpus' / 'ami' / 'video'
        video.mkdir(parents=True)               # the Corner-era default dir: exists, EMPTY
        rows = make_corpus(full, ['EN2001a.avi', 'ES2002a.avi', 'IS1000a.avi'])
        man = d / 'ami_video_manifest.jsonl'
        write_manifest(man, rows)               # unstamped, like the manifest built at B3
        M = ['--manifest', str(man)]

        print('STEP 0 AS IT DIED — --verify pointed at the wrong directory, staged rows (url \'\')')
        rc, out = run(['--verify', *M, '--corpus-dir', str(video)])
        check('wrong dir -> NOT DONE, rc=1, never reaches the network',
              rc == 1 and 'NOT DONE' in out and 'NETWORK TOUCHED' not in out, f'rc={rc}\n{out}')
        check('...names the missing file AND the directory it looked in',
              'EN2001a.avi' in out and str(video) in out, out)
        check('...says a verify never fetches and names the two real remedies',
              'never fetches' in out and '--fetch-missing' in out and '--corpus-dir' in out, out)
        check('...no .part file was created', not list(video.glob('*.part')))

        print('\nTHE RULE: no default that names a corpus')
        rc, out = run(['--verify', *M])
        check('unstamped manifest + no --corpus-dir -> REFUSES, names the stamp command',
              rc == 1 and '--stamp-corpus-dir' in out and 'corpus/ami/video' in out, f'rc={rc}\n{out}')
        rc, out = run(['--build-manifest', *M, '--measured-dpf', '7.77',
                       '--measured-chars-per-det', '222.2'])
        check('--build-manifest without --corpus-dir -> REFUSES', rc == 1 and 'corpus-dir' in out, f'rc={rc}\n{out}')

        print('\nVERIFY, right directory')
        rc, out = run(['--verify', *M, '--corpus-dir', str(full)])
        check('--verify (sha256) right dir -> DONE 3/3, rc=0, no network',
              rc == 0 and 'DONE verified=3/3' in out and 'sha256' in out and 'NETWORK' not in out, f'rc={rc}\n{out}')
        check('...banner names the operation as read-only and the dir source',
              'read-only, never fetches' in out and 'records none' in out, out)
        rc, out = run([*M, '--corpus-dir', str(full)])
        check('no flag = size-only verify, DONE, no network',
              rc == 0 and 'size only' in out and 'NETWORK' not in out, f'rc={rc}\n{out}')

        print('\nFETCH-MISSING — the only operation allowed to touch the network')
        (full / 'IS1000a.avi').rename(d / 'parked.avi')
        rc, out = run(['--fetch-missing', *M, '--corpus-dir', str(full)])
        check('staged row missing -> REFUSES by name, "NEVER fetched", no network',
              rc == 1 and 'IS1000a.avi' in out and 'NEVER fetched' in out and 'NETWORK' not in out, f'rc={rc}\n{out}')
        (d / 'parked.avi').rename(full / 'IS1000a.avi')
        # a row WITH a url, missing: fetch IS called (provisioning still works)
        rows_url = [dict(r) for r in rows]
        rows_url[0]['url'] = 'https://mirror.example/EN2001a.avi'
        man_u = d / 'm_url.jsonl'; write_manifest(man_u, rows_url)
        (full / 'EN2001a.avi').rename(d / 'parked.avi')
        called = []
        def fake_fetch(url, dest, timeout=120):
            called.append(url); dest.write_bytes((d / 'parked.avi').read_bytes()); return True
        rc, out = run(['--fetch-missing', '--manifest', str(man_u), '--corpus-dir', str(full)], fetch=fake_fetch)
        check('--fetch-missing with a url row -> fetches exactly that row, then size-checks DONE',
              rc == 0 and called == ['https://mirror.example/EN2001a.avi'] and 'DONE' in out, f'rc={rc} called={called}\n{out}')
        (d / 'parked.avi').unlink()
        try:
            fav.fetch_url = fav.__dict__['fetch_url']  # restore the real one for the guard test
        except Exception:
            pass
        import importlib; importlib.reload(fav)
        try:
            fav.fetch_url('', Path('/tmp/x.avi')); check('fetch_url("") raises structurally', False, 'it returned')
        except ValueError as e:
            check('fetch_url("") raises structurally, before any network', 'never fetched' in str(e))

        print('\nSTAMP — the field is EARNED by a full sha256 verify, and only the meta line moves')
        before_data, before_sha = data_lines(man), hashlib.sha256(man.read_bytes()).hexdigest()
        rc, out = run(['--stamp-corpus-dir', *M, '--corpus-dir', str(full)])
        meta = loc.read_meta(man)
        check('stamp right dir -> rc=0, meta gains corpus_dir (absolute), proof recorded',
              rc == 0 and meta.get('corpus_dir') == str(full.resolve())
              and 'sha256 verify 3/3' in json.dumps(meta.get('corpus_dir_stamped')), f'rc={rc}\n{out}\n{meta}')
        check('...data rows byte-identical, manifest sha changed and both printed',
              data_lines(man) == before_data and hashlib.sha256(man.read_bytes()).hexdigest() != before_sha
              and before_sha[:16] in out, out)
        rc, out = run(['--verify', *M])
        check('after stamp: --verify with NO --corpus-dir derives it from the meta -> DONE',
              rc == 0 and '[manifest meta]' in out and 'DONE verified=3/3' in out, f'rc={rc}\n{out}')
        rc, out = run(['--verify', *M, '--corpus-dir', str(video)])
        check('after stamp: a DISAGREEING --corpus-dir -> REFUSES as drift, naming both, no network',
              rc == 1 and 'drift' in out and str(video) in out and str(full.resolve()) in out
              and 'NETWORK' not in out, f'rc={rc}\n{out}')
        rc, out = run(['--verify', *M, '--corpus-dir', str(full / '..' / 'full')])
        check('after stamp: an AGREEING --corpus-dir spelled differently -> ok',
              rc == 0 and 'agrees' in out, f'rc={rc}\n{out}')

        print('\nSTAMP null controls')
        bad_dir = d / 'corrupt'   # SAME length, different bytes: only sha256 can tell
        make_corpus(bad_dir, ['EN2001a.avi', 'ES2002a.avi', 'IS1000a.avi'], content=b'XVI-BYTES-')
        snap = man.read_bytes()
        rc, out = run(['--stamp-corpus-dir', *M, '--corpus-dir', str(bad_dir)])
        check('stamp against same-size DIFFERENT bytes -> sha256 mismatch, NOT DONE, manifest UNTOUCHED',
              rc == 1 and 'sha256 mismatch' in out and man.read_bytes() == snap, f'rc={rc}\n{out}')
        rc, out = run(['--stamp-corpus-dir', *M])
        check('stamp without --corpus-dir -> refuses (an explicit intent, never derived)',
              rc == 1 and 'explicit' in out, f'rc={rc}\n{out}')
        rc, out = run(['--verify', '--fetch-missing', *M, '--corpus-dir', str(full)])
        check('two operations at once -> refuses', rc == 1 and 'one operation' in out, f'rc={rc}\n{out}')

        print('\nLOCATOR CLI (what run_plan calls)')
        import subprocess
        r = subprocess.run([sys.executable, str(HERE / 'corpus_locator.py'), '--manifest', str(man)],
                           capture_output=True, text=True)
        lines = r.stdout.strip().splitlines()
        check('stamped manifest -> stdout line 1 = path, line 2 = source, rc=0',
              r.returncode == 0 and len(lines) == 2 and Path(lines[0]).resolve() == full.resolve()
              and lines[1] == 'manifest meta', f'rc={r.returncode}\n{r.stdout}{r.stderr}')
        write_manifest(man, rows)  # back to unstamped
        r = subprocess.run([sys.executable, str(HERE / 'corpus_locator.py'), '--manifest', str(man)],
                           capture_output=True, text=True)
        check('unstamped + no env -> rc=1, names the stamp command (run_plan refuses to launch)',
              r.returncode == 1 and '--stamp-corpus-dir' in r.stdout, f'rc={r.returncode}\n{r.stdout}')
        r = subprocess.run([sys.executable, str(HERE / 'corpus_locator.py'), '--manifest', str(man),
                            '--corpus-dir', str(full)], capture_output=True, text=True)
        check('unstamped + CORPUS_DIR env -> accepted, source says the meta records none',
              r.returncode == 0 and 'records none' in r.stdout, f'rc={r.returncode}\n{r.stdout}')

    print('\nSTATIC — the three consumers carry no default that names a corpus')
    for name in ('driver_video.py', 'smoke_video.py'):
        src = (HERE / name).read_text()
        m = re.search(r"add_argument\('--corpus-dir',\s*default=([^,\)]+)", src)
        check(f'{name}: --corpus-dir default is None', m is not None and m.group(1).strip() == 'None',
              m.group(0) if m else 'no --corpus-dir argument found')
        check(f'{name}: calls resolve_corpus_dir', 'resolve_corpus_dir(' in src)
    src = (HERE / 'fetch_ami_video.py').read_text()
    check('fetch_ami_video.py: CORPUS has no default path',
          re.search(r'^CORPUS: Path \| None = None', src, re.M) is not None)
    sh = (HERE / 'run_plan.sh').read_text()
    for tool in ('fetch_ami_video.py --verify', 'smoke_video.py', 'driver_video.py --out-dir'):
        idx = sh.index(tool)
        window = sh[idx: idx + 400]
        check(f'run_plan passes --manifest and --corpus-dir to {tool.split()[0]}',
              '--manifest "$VIDEO_MANIFEST"' in window and '--corpus-dir "$CORPUS_DIR"' in window, window[:200])
    check('run_plan resolves through corpus_locator, not a literal path',
          'corpus_locator.py' in sh and 'corpus/ami/video' not in re.sub(r'#[^\n]*', '', sh))

    print(f'\ncorpus-locator site controls: {"PASS" if not FAILS else "FAIL"} ({len(FAILS)} failing)')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
