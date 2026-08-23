#!/usr/bin/env python3
"""Every cross-arm comparator, exercised against the 2026-08-23 stale-artifact
scenario and its null controls.

Run:  python3 test_artifact_identity_sites.py        (no box, no venv, no docker)

Why this file is separate from artifact_identity's own --self-test: that one
proves the SELECTOR is correct; this one proves each CALL SITE actually uses
it. Four sites had the same defect and three were patched one at a time, each
at the site where the failure had been observed — so the property worth testing
is not "the helper works" but "no site compares without it".

The shell blocks are extracted from the LIVE probe_run.sh on every run and fed
on stdin exactly as the script feeds them. A snapshot would be a stale copy, and
this harness was testing one until it was caught mid-build.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAILS: list[str] = []
CORNER = 'c0rnerc0rnerc0rn'


def check(name: str, cond: bool, detail: str = '') -> None:
    if not cond:
        FAILS.append(name)
    print(f'  {"ok  " if cond else "FAIL"} {name}' + (f'\n       {detail}' if not cond else ''))


def block(marker: str) -> str:
    sh = (HERE / 'probe_run.sh').read_text()
    body = sh.split(f"<<'{marker}'", 1)[1].split('\n', 1)[1]
    return body.split(f'\n{marker}\n', 1)[0]


def run_block(marker: str, cwd: Path, *args) -> tuple[int, str]:
    r = subprocess.run([sys.executable, '-', *map(str, args)], cwd=cwd,
                       input=block(marker), capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def fixture(d: Path, *, fresh_floor=True, corrupt=None, rr_frames=93, stale=True,
            rr_fresh=True, rr_labels=None, li_labels=None) -> Path:
    (d / 'artifact_identity.py').write_bytes((HERE / 'artifact_identity.py').read_bytes())
    vid = d / 'ES2009a.avi'
    vid.write_bytes(b'FRESH-VIDEO-BYTES' * 100)
    want = hashlib.sha256(vid.read_bytes()).hexdigest()[:16]
    eng = [f'{i:016x}' for i in range(93)]
    (d / 'probe_frame_identity_early.json').write_text(json.dumps(
        {'video': 'ES2009a.avi', 'video_sha16': want, 'engine_frame_png_sha16': eng}))
    li = list(eng)
    if corrupt is not None:
        li[corrupt] = 'f' * 16
    labels_li = li_labels if li_labels is not None else [['chair'], ['person']]
    labels_rr = rr_labels if rr_labels is not None else [['chair'], ['person']]
    if fresh_floor:
        (d / 'probe_li_floor_t2.json').write_text(json.dumps(
            {'video': 'ES2009a.avi', 'video_sha16': want, 'n_frames': 93,
             'frame_png_sha16': li, 'frame_label_multisets': labels_li,
             'frame_scores': [[0.9], [0.9]]}))
    if stale:   # the exact Corner layout — t8 sorts LAST, which is what broke it
        for t in (1, 8, 32):
            (d / f'probe_li_floor_t{t}.json').write_text(json.dumps(
                {'video': 'ES2002a.Corner.avi', 'video_sha16': CORNER, 'n_frames': 83,
                 'frame_png_sha16': [f'{i:016x}' for i in range(83)]}))
        (d / 'probe_rr_t8.json').write_text(json.dumps(
            {'video': '/c/ES2002a.Corner.avi', 'video_sha16': CORNER,
             'sends': [{'label': 'steady-state', 'documents': {
                 'frames_rawdecode': 83, 'frames_from_chunks': 83,
                 'frame_label_multisets': [['chair']] * 83}}]}))
    if rr_fresh:
        (d / 'probe_rr_t2.json').write_text(json.dumps(
            {'video': '/c/ES2009a.avi', 'video_sha16': want,
             'sends': [{'label': 'steady-state', 'documents': {
                 'frames_rawdecode': rr_frames, 'frames_from_chunks': rr_frames,
                 'total_chars': 165000,
                 'frame_label_multisets': labels_rr, 'frame_scores': [[0.9], [0.9]]}}]}))
    return vid


def main() -> int:
    print('GATE 4 — the scenario that reported a decode failure for a correct decode')
    with tempfile.TemporaryDirectory() as t:
        d = Path(t); vid = fixture(d)
        rc, out = run_block('EOF4', d, vid, '2')
        check('fresh t2 beside stale t1/t8/t32 -> PASS on 93 (was FAIL 93 vs 83)',
              rc == 0 and '93 frames byte-identical' in out, f'rc={rc}\n{out}')
        check('the log ALWAYS names the artifact it compared against',
              'selected by identity: probe_li_floor_t2.json' in out, out)
    with tempfile.TemporaryDirectory() as t:
        d = Path(t); vid = fixture(d)
        (d / 'probe_li_floor_t4.json').write_bytes((d / 'probe_li_floor_t2.json').read_bytes())
        (d / 'probe_li_floor_t2.json').unlink()
        rc, out = run_block('EOF4', d, vid, '2')
        check("this run's matrix point absent -> falls back within THIS video, named",
              rc == 0 and 'probe_li_floor_t4.json' in out, f'rc={rc}\n{out}')
    with tempfile.TemporaryDirectory() as t:
        d = Path(t); vid = fixture(d, corrupt=7)
        rc, out = run_block('EOF4', d, vid, '2')
        check('NULL CONTROL: a corrupted hash -> REAL DIFFERENCE, rc=1',
              rc == 1 and 'REAL DIFFERENCE' in out and 'CANNOT COMPARE' not in out, f'rc={rc}\n{out}')
    with tempfile.TemporaryDirectory() as t:
        d = Path(t); vid = fixture(d, fresh_floor=False)
        rc, out = run_block('EOF4', d, vid, '2')
        check('only stale floors -> CANNOT COMPARE, rc=2, defers',
              rc == 2 and 'CANNOT COMPARE' in out and 'DEFERS' in out, f'rc={rc}\n{out}')
        check('...and never claims a real difference or quotes a foreign frame count',
              'REAL DIFFERENCE' not in out and 'n_li=83' not in out, out)
        check('...and names every rejected candidate', out.count(CORNER) >= 3, out)

    print('\nGATE 3 — a stale artifact and arm disagreement must not read the same')
    with tempfile.TemporaryDirectory() as t:
        d = Path(t); vid = fixture(d)
        rc, out = run_block('EOF3', d, vid, '2')
        check('matching arms -> PASS, with both required read-back lines',
              rc == 0 and 'both arms confirmed on ES2009a.avi' in out
              and 'EXACT agreement on 2 frames' in out, f'rc={rc}\n{out}')
    with tempfile.TemporaryDirectory() as t:
        d = Path(t); vid = fixture(d, rr_labels=[['chair'], ['laptop']])
        rc, out = run_block('EOF3', d, vid, '2')
        check('NULL CONTROL: genuine label divergence -> REAL DIFFERENCE, rc=1, UNARMED',
              rc == 1 and 'REAL DIFFERENCE' in out and 'UNARMED' in out, f'rc={rc}\n{out}')
    with tempfile.TemporaryDirectory() as t:
        d = Path(t); vid = fixture(d)
        doc = json.loads((d / 'probe_rr_t2.json').read_text())
        doc['video_sha16'] = CORNER                      # stale RR arm
        (d / 'probe_rr_t2.json').write_text(json.dumps(doc))
        rc, out = run_block('EOF3', d, vid, '2')
        check('stale arm -> CANNOT COMPARE, rc=2, names the side, NOT a disagreement',
              rc == 2 and 'CANNOT COMPARE' in out and 'rr' in out
              and 'REAL DIFFERENCE' not in out, f'rc={rc}\n{out}')
    with tempfile.TemporaryDirectory() as t:
        d = Path(t); vid = fixture(d)
        (d / 'probe_rr_t2.json').unlink()
        rc, out = run_block('EOF3', d, vid, '2')
        check('missing matrix point -> CANNOT COMPARE, no substitute is reached for',
              rc == 2 and 'CANNOT COMPARE' in out, f'rc={rc}\n{out}')

    print('\nFRAME AGREEMENT — the block whose rc is the probe\'s exit code')
    with tempfile.TemporaryDirectory() as t:
        d = Path(t); vid = fixture(d)
        rc, out = run_block('EOF', d, vid)
        check('stale 83-frame artifacts excluded -> PASS on [93] (was NOT CONFIRMED)',
              rc == 0 and 'PASS' in out and '[93]' in out, f'rc={rc}\n{out}')
        check('...and the exclusions are stated, never silent', 'EXCLUDED' in out, out)
    with tempfile.TemporaryDirectory() as t:
        d = Path(t); vid = fixture(d, rr_frames=92)
        rc, out = run_block('EOF', d, vid)
        check('NULL CONTROL: real 92-vs-93 disagreement -> REAL DIFFERENCE, rc=1',
              rc == 1 and 'REAL DIFFERENCE' in out, f'rc={rc}\n{out}')
    with tempfile.TemporaryDirectory() as t:
        d = Path(t); vid = fixture(d, fresh_floor=False, rr_fresh=False)
        rc, out = run_block('EOF', d, vid)
        check('nothing from this video -> CANNOT COMPARE, no fabricated finding',
              rc == 2 and 'CANNOT COMPARE' in out and 'REAL DIFFERENCE' not in out, f'rc={rc}\n{out}')

    print('\nTHREAD CURVE — it emits the two values that re-cut the manifest')
    def curve(d, *a):
        r = subprocess.run([sys.executable, str(HERE / 'summarize_probe_rr.py'), str(d), *a],
                           capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr
    with tempfile.TemporaryDirectory() as t:
        d = Path(t); fixture(d)
        rc, out = curve(d)
        check('two videos on disk -> REFUSES to pool, rc=2', rc == 2 and 'CANNOT COMPARE' in out,
              f'rc={rc}\n{out}')
        check('...naming the manifest re-cut as the stake', 'measured-dpf' in out, out)
        check('...and emitting no dpf value while refusing', '\n  --measured-dpf' not in out, out)
        rc2, out2 = curve(d, '--all-videos')
        check('--all-videos pools deliberately and declares which videos',
              rc2 == 0 and 'pooling DECLARED' in out2 and 'ES2002a.Corner.avi' in out2,
              f'rc={rc2}\n{out2}')
    with tempfile.TemporaryDirectory() as t:
        d = Path(t); fixture(d, stale=False)
        rc, out = curve(d)
        check('one video -> proceeds and prints the re-cut inputs', rc == 0 and 'measured-dpf' in out,
              f'rc={rc}\n{out}')

    print('\nSELECTOR self-test (artifact_identity --self-test)')
    r = subprocess.run([sys.executable, str(HERE / 'artifact_identity.py'), '--self-test'],
                       capture_output=True, text=True)
    check('selector self-test passes', r.returncode == 0, r.stdout + r.stderr)

    print(f'\ncall-site controls: {"PASS" if not FAILS else "FAIL"} ({len(FAILS)} failing)')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
