#!/usr/bin/env python3
"""ONE selector and ONE verdict vocabulary for every cross-arm artifact.

WHY THIS FILE EXISTS (2026-08-23 — the same defect at four call sites)
---------------------------------------------------------------------
`sorted(glob('probe_li_floor_t*.json'))[-1]` is LEXICOGRAPHIC: with
t1/t2/t8/t32 on disk it returns **t8**, not t32 and not "the newest".  Four
sites loaded a cross-arm artifact that way, and each fix was applied at the
site where the failure had been OBSERVED — so the identical defect resurfaced
one site later, on the next corpus, three times running:

    probe_frame_identity.py   early identity      patched 4c659541
    probe_run.sh              gate-3 staging      patched 78d630f0
    probe_run.sh              gate-4 compare      BROKEN until this file
    probe_run.sh              frame agreement     BROKEN until this file

Register entry 6's addendum names the cure: not "fix all four" but HAVE ONE
COPY.  Every site now calls select_by_video()/select_all_by_video()/
require_same_video() here, so a fifth site cannot be written without one.

Note what the ordering hypothesis would have cost: "take the newest instead"
is an ORDERING fix for an IDENTITY bug.  It happens to pick the right file
today and silently picks the wrong one the first time a probe is re-run out
of order, or a floor is copied in, or the clock moves.  Identity is not a
sort key.

THE SECOND HALF: A VERDICT IS NOT A DIFFERENCE UNTIL SAME-INPUT IS PROVEN
------------------------------------------------------------------------
The standing policy "on a cross-arm mismatch the REAL-DIFFERENCE hypothesis
comes first, never tolerance" is correct — and it assumes both sides read the
same input.  When the comparator cannot prove that, the finding is NOT a real
difference; it is that the comparator CANNOT COMPARE.  Those two printed the
same sentence, so a true positive and a stale-file bug were indistinguishable
in the log.  They are now different verdicts with different exit codes, and
real_difference() REFUSES to render without the sha16 that proves same-input.

Exit codes:  0 PASS   1 REAL DIFFERENCE (same input proven)   2 CANNOT COMPARE
"""
from __future__ import annotations

import glob as _glob
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable, NamedTuple

RC_PASS, RC_REAL_DIFFERENCE, RC_CANNOT_COMPARE = 0, 1, 2

ABSENT = 'ABSENT (pre-2026-08-23 artifact: recorded no video_sha16)'
UNREADABLE = 'UNREADABLE (not loadable as json)'
_SHA16 = re.compile(r'^[0-9a-f]{16}$')


def video_sha16(video: str | Path) -> str:
    """The identity of the input file. Same 16 hex chars every producer records."""
    return hashlib.sha256(Path(video).read_bytes()).hexdigest()[:16]


class Rejected(NamedTuple):
    file: str
    video_sha16: str

    def __repr__(self) -> str:            # so log lines read as themselves
        return f'{self.file} -> {self.video_sha16}'


class Selection(NamedTuple):
    path: str | None
    doc: dict
    rejected: list           # list[Rejected] — every candidate NAMED, never silent
    want_sha: str

    @property
    def ok(self) -> bool:
        return self.path is not None

    def rejected_json(self):
        return [{'file': r.file, 'video_sha16': r.video_sha16} for r in self.rejected] or None

    def why_not(self, video_name: str = '') -> str:
        seen = ', '.join(repr(r) for r in self.rejected) or 'no candidate files on disk'
        return (f'no artifact recorded from THIS video (sha16 {self.want_sha}'
                f'{" = " + video_name if video_name else ""}); candidates rejected: {seen}')


def _candidates(patterns: Iterable[str], where: Path) -> list[str]:
    out: list[str] = []
    for pat in patterns:
        out.extend(sorted(_glob.glob(str(where / pat))))
    return out


def _load(cand: str):
    try:
        with open(cand) as fh:
            return json.load(fh)
    except Exception:                      # noqa: BLE001 — unreadable is REJECTED and named
        return None


def _identity_of(doc: dict) -> str:
    got = doc.get('video_sha16')
    return ABSENT if got is None else str(got)


def select_by_video(want_sha: str, patterns: Iterable[str], where: str | Path = '.',
                    explicit: str | None = None) -> Selection:
    """The one artifact produced from THIS video. Never a sort order.

    `explicit` (an operator-passed path) is still checked: an explicitly named
    file from the wrong video is the same bug with a human in the loop.
    """
    where = Path(where)
    cands = [explicit] if explicit else _candidates(patterns, where)
    rejected: list[Rejected] = []
    for cand in cands:
        if not cand or not Path(cand).exists():
            continue
        doc = _load(cand)
        if doc is None:
            rejected.append(Rejected(Path(cand).name, UNREADABLE))
            continue
        if _identity_of(doc) == want_sha:
            return Selection(cand, doc, rejected, want_sha)
        rejected.append(Rejected(Path(cand).name, _identity_of(doc)))
    return Selection(None, {}, rejected, want_sha)


def select_all_by_video(want_sha: str, patterns: Iterable[str],
                        where: str | Path = '.') -> tuple[list[tuple[str, dict]], list[Rejected]]:
    """Every artifact from THIS video, plus every rejection, named.

    For checks that pool many files (frame-count agreement across methods).
    Pooling without this turns one stale Corner floor into a fabricated
    "the methods disagree" — a wrong answer that reads like a real finding.
    """
    kept: list[tuple[str, dict]] = []
    rejected: list[Rejected] = []
    for cand in _candidates(patterns, Path(where)):
        doc = _load(cand)
        if doc is None:
            rejected.append(Rejected(Path(cand).name, UNREADABLE))
        elif _identity_of(doc) == want_sha:
            kept.append((cand, doc))
        else:
            rejected.append(Rejected(Path(cand).name, _identity_of(doc)))
    return kept, rejected


def require_same_video(want_sha: str, named_docs: dict) -> str | None:
    """None when every side proves THIS video; otherwise the reason, naming the side."""
    for name, doc in named_docs.items():
        got = _identity_of(doc)
        if got == ABSENT:
            return (f'{name} recorded no video_sha16 — it cannot prove which video it read '
                    '(artifact predates 2026-08-23; re-run with the current probes)')
        if got != want_sha:
            return (f'{name} was produced from a DIFFERENT video (recorded {got}, '
                    f'this run {want_sha})')
    return None


# ---- verdict vocabulary --------------------------------------------------
# A comparator prints exactly one of these three. The distinction is the point:
# CANNOT COMPARE is a fault in the EVIDENCE, REAL DIFFERENCE is a finding about
# the ARMS, and until 2026-08-23 they printed the same sentence.

def cannot_compare(gate: str, why: str) -> str:
    return (f'{gate}: CANNOT COMPARE — {why}.\n'
            f'{gate}: this is NOT a real-difference finding and NOT a tolerance question. '
            'The comparator could not prove both sides read the same input, so it has no '
            'verdict to give. Fix the evidence, then re-run.')


def real_difference(gate: str, what: str, proven_sha: str) -> str:
    """Refuses to render without the sha16 that proves same-input on both sides.

    Structural, not remembered: the only way to print the real-difference
    sentence is to hold the proof that entitles you to it.
    """
    if not (isinstance(proven_sha, str) and _SHA16.match(proven_sha)):
        raise ValueError(
            'real_difference() requires the video_sha16 PROVEN on both sides; got '
            f'{proven_sha!r}. If you cannot prove same-input, the verdict is '
            'cannot_compare() — see this module\'s docstring.')
    return (f'{gate}: FAIL — {what}.\n'
            f'{gate}: same input PROVEN on both sides (video_sha16 {proven_sha}), so this is a '
            'REAL DIFFERENCE. Hypothesis order: decode path / ffmpeg build / model or '
            'serving stack — never tolerance.')


def passed(gate: str, what: str, proven_sha: str) -> str:
    if not (isinstance(proven_sha, str) and _SHA16.match(proven_sha)):
        raise ValueError('passed() requires the proven video_sha16')
    return f'{gate}: PASS — {what} (video_sha16 {proven_sha})'


# ---- self-test -----------------------------------------------------------
# Null-controlled, per the standing rule that a checker which cannot fail is
# not a checker. Control 1 asserts the TRAP as well as the fix: it proves
# `sorted(glob)[-1]` really does return t8 on this layout, so the test would
# notice if the defect it guards against ever stopped being reproducible.
def _self_test() -> int:
    import tempfile
    fails = []

    def check(name, cond, detail=''):
        fails.append(f'{name}: {detail}') if not cond else None
        print(f'  {"ok  " if cond else "FAIL"} {name}' + (f' — {detail}' if not cond else ''))

    FRESH, CORNER = 'a1b2c3d4e5f60718', '0f1e2d3c4b5a6978'
    with tempfile.TemporaryDirectory() as d:
        dd = Path(d)
        def write(name, doc):
            (dd / name).write_text(json.dumps(doc))
        # The exact 2026-08-23 layout: fresh t2, stale Corner t1/t8/t32.
        write('probe_li_floor_t1.json',  {'video_sha16': CORNER, 'n_frames': 83})
        write('probe_li_floor_t2.json',  {'video_sha16': FRESH,  'n_frames': 93})
        write('probe_li_floor_t8.json',  {'video_sha16': CORNER, 'n_frames': 83})
        write('probe_li_floor_t32.json', {'video_sha16': CORNER, 'n_frames': 83})

        lex_last = sorted(_glob.glob(str(dd / 'probe_li_floor_t*.json')))[-1]
        check('control: the trap reproduces (lexicographic last IS t8)',
              Path(lex_last).name == 'probe_li_floor_t8.json', f'got {Path(lex_last).name}')

        sel = select_by_video(FRESH, ['probe_li_floor_t*.json'], dd)
        check('picks by identity, not sort order',
              sel.ok and Path(sel.path).name == 'probe_li_floor_t2.json' and sel.doc['n_frames'] == 93,
              f'got {sel.path}')
        check('every rejected candidate is NAMED',
              len(sel.rejected) >= 1 and all(r.video_sha16 == CORNER for r in sel.rejected),
              f'got {sel.rejected}')

        write('probe_li_floor_t4.json', {'n_frames': 83})            # pre-2026-08-23
        old = select_by_video('deadbeefdeadbeef', ['probe_li_floor_t4.json'], dd)
        check('artifact with no video_sha16 is named ABSENT, not skipped silently',
              any(r.video_sha16 == ABSENT for r in old.rejected), f'got {old.rejected}')

        nomatch = select_by_video('cafebabecafebabe', ['probe_li_floor_t*.json'], dd)
        check('no matching artifact -> not ok (defer), with all candidates named',
              (not nomatch.ok) and len(nomatch.rejected) == 5, f'got {nomatch.rejected}')
        check('why_not() names the wanted sha and the rejections',
              'cafebabecafebabe' in nomatch.why_not() and 'probe_li_floor_t8' in nomatch.why_not())

        (dd / 'probe_li_floor_t99.json').write_text('{not json')
        bad = select_by_video('cafebabecafebabe', ['probe_li_floor_t99.json'], dd)
        check('unreadable json is rejected and named, never a crash',
              (not bad.ok) and bad.rejected[0].video_sha16 == UNREADABLE, f'got {bad.rejected}')

        explicit = select_by_video(FRESH, [], dd, explicit=str(dd / 'probe_li_floor_t8.json'))
        check('an EXPLICIT path from the wrong video is still refused',
              not explicit.ok, f'got {explicit.path}')

        kept, rej = select_all_by_video(FRESH, ['probe_li_floor_t*.json'], dd)
        check('pooling keeps only THIS video (frame-agreement case)',
              len(kept) == 1 and {k[1]['n_frames'] for k in kept} == {93}
              and len(rej) == 5, f'kept={[Path(k).name for k,_ in kept]} rejected={rej}')

    check('require_same_video passes when both sides prove it',
          require_same_video(FRESH, {'engine': {'video_sha16': FRESH},
                                     'li_floor': {'video_sha16': FRESH}}) is None)
    r = require_same_video(FRESH, {'engine': {'video_sha16': FRESH},
                                   'li_floor': {'video_sha16': CORNER}})
    check('require_same_video names the offending SIDE', r is not None and 'li_floor' in r, f'got {r}')
    r2 = require_same_video(FRESH, {'engine': {'video_sha16': FRESH}, 'li_floor': {}})
    check('require_same_video distinguishes ABSENT from mismatched',
          r2 is not None and 'no video_sha16' in r2, f'got {r2}')

    # NULL CONTROLS on the vocabulary itself.
    for bogus in (None, '', 'not-a-sha', 'A1B2C3D4E5F60718', FRESH * 4):
        try:
            real_difference('gate 4', 'x', bogus)
            check(f'real_difference REFUSES unproven input ({bogus!r})', False, 'it rendered')
        except ValueError:
            check(f'real_difference REFUSES unproven input ({bogus!r})', True)
    check('real_difference renders when proof is held',
          'REAL DIFFERENCE' in real_difference('gate 4', 'x', FRESH))
    check('cannot_compare NEVER says real difference',
          'REAL DIFFERENCE' not in cannot_compare('gate 4', 'why').upper().replace('NOT A REAL-DIFFERENCE', ''))
    check('cannot_compare says so in its first line',
          cannot_compare('gate 4', 'why').splitlines()[0].startswith('gate 4: CANNOT COMPARE'))
    check('the two verdicts are textually distinguishable',
          'CANNOT COMPARE' not in real_difference('gate 4', 'x', FRESH))

    print(f'\nartifact_identity self-test: {"PASS" if not fails else "FAIL"} '
          f'({len(fails)} failing)')
    return 1 if fails else 0


if __name__ == '__main__':
    import sys
    if '--self-test' in sys.argv:
        raise SystemExit(_self_test())
    print(__doc__)
