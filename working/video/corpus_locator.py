#!/usr/bin/env python3
"""ONE answer to "where is the corpus" — for every tool, and for run_plan.

WHY (2026-08-23, the campaign died at step 0 four minutes in, nothing measured)
-----------------------------------------------------------------------------
Three tools carried three private copies of ``ROOT/corpus/ami/video`` as their
--corpus-dir default, and run_plan.sh passed --corpus-dir to NONE of them. The
default was right for the Corner corpus and silently wrong for ami_full
(corpus/ami/full): step 0's verify found every file "missing", and the tool's
answer to "not found" was to reach for the network — urlopen('') on a staged
row. The smoke and the driver carried the same default and would have died the
same way, one step at a time, each asking for one more flag. Same shape as the
PDF corpus on 2026-08-22 and the golden path the same night: a default that was
correct for one corpus, plus a tool that fetches when it should refuse.

THE RULE
--------
NO tool carries a default that names a corpus. The manifest records the
directory it was built (or stamped) against — ``_meta.corpus_dir`` — and every
consumer derives from that. An explicit --corpus-dir must AGREE with it; a
manifest without the field REFUSES and names the stamp command. The three tools
cannot drift from each other because none of them holds its own copy, and they
cannot drift from the manifest because the manifest is where the value lives.

Precedence:  explicit --corpus-dir (checked against meta)  >  meta  >  REFUSE.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

META_KEY = 'corpus_dir'
STAMP_CMD = ('python working/video/fetch_ami_video.py --stamp-corpus-dir '
             '--corpus-dir <the directory the 170 files are in>')


class CorpusDirError(SystemExit):
    """NOT DONE, with the reason. Subclasses SystemExit so an uncaught one exits
    1 printing the message — the driver's house style — while fetch/smoke can
    catch it and report in theirs."""

    def __init__(self, msg: str):
        super().__init__(f'NOT DONE — {msg}')
        self.msg = msg


def read_meta(manifest: Path) -> dict:
    try:
        first = next((l for l in manifest.read_text().splitlines() if l.strip()), '')
        doc = json.loads(first) if first else {}
    except (OSError, json.JSONDecodeError):
        return {}
    return doc.get('_meta', {}) if isinstance(doc, dict) else {}


def manifest_corpus_dir(meta: dict) -> Path | None:
    v = (meta or {}).get(META_KEY)
    return Path(v) if v else None


def resolve_corpus_dir(explicit: str | None, meta: dict, manifest: Path,
                       tool: str = 'this tool') -> tuple[Path, str]:
    """Returns (corpus_dir, source). Raises CorpusDirError rather than default.

    source is 'explicit (agrees with manifest meta)', 'manifest meta', or
    'explicit (manifest records none)' — always printed by the caller so the
    log shows WHERE the path came from, not only what it was.
    """
    recorded = manifest_corpus_dir(meta)
    if explicit:
        exp = Path(explicit).expanduser()
        if recorded is not None and exp.resolve() != recorded.resolve():
            raise CorpusDirError(
                f'{tool}: --corpus-dir {exp} does not agree with the manifest, which records '
                f'{META_KEY}={recorded} ({manifest.name}). Two paths for one corpus is the '
                f'drift this check exists for. If the corpus MOVED, re-stamp: {STAMP_CMD}')
        if not exp.is_dir():
            raise CorpusDirError(f'{tool}: --corpus-dir {exp} is not a directory')
        return exp, ('explicit (agrees with manifest meta)' if recorded is not None
                     else 'explicit (manifest records none — stamp it so run_plan can derive it)')
    if recorded is not None:
        if not recorded.is_dir():
            raise CorpusDirError(
                f'{tool}: the manifest records {META_KEY}={recorded} but it is not a directory '
                f'here. The manifest was stamped on another layout; re-stamp: {STAMP_CMD}')
        return recorded, 'manifest meta'
    raise CorpusDirError(
        f'{tool}: no --corpus-dir given and {manifest.name} records no {META_KEY} (built before '
        f'2026-08-23). Refusing to default — the default was corpus/ami/video, correct for the '
        f'Corner corpus and silently wrong for this one. Stamp the manifest ONCE, after a full '
        f'sha256 verify proves the directory holds what the manifest describes: {STAMP_CMD}')


def _self_test() -> int:
    import tempfile
    fails = []

    def check(name, cond, detail=''):
        if not cond:
            fails.append(name)
        print(f'  {"ok  " if cond else "FAIL"} {name}' + (f' — {detail}' if not cond else ''))

    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        full, video = d / 'corpus' / 'ami' / 'full', d / 'corpus' / 'ami' / 'video'
        full.mkdir(parents=True); video.mkdir(parents=True)
        man = d / 'm.jsonl'

        # 1. unstamped manifest, no flag -> REFUSE naming the stamp command (never default)
        man.write_text(json.dumps({'_meta': {'built_utc': 'x'}}) + '\n{"file":"a.avi"}\n')
        try:
            resolve_corpus_dir(None, read_meta(man), man, 'T'); check('unstamped+noflag refuses', False)
        except CorpusDirError as e:
            check('unstamped + no flag -> REFUSES, names the stamp command',
                  '--stamp-corpus-dir' in str(e) and 'corpus/ami/video' in str(e), str(e))

        # 2. unstamped, explicit -> accepted, source says the meta records none
        p, src = resolve_corpus_dir(str(full), read_meta(man), man, 'T')
        check('unstamped + explicit -> accepted, source names the gap',
              p == full and 'records none' in src, f'{p} {src}')

        # 3. stamped, no flag -> meta
        man.write_text(json.dumps({'_meta': {META_KEY: str(full.resolve())}}) + '\n{"file":"a.avi"}\n')
        p, src = resolve_corpus_dir(None, read_meta(man), man, 'T')
        check('stamped + no flag -> manifest meta', p.resolve() == full.resolve() and src == 'manifest meta', f'{p} {src}')

        # 4. stamped, explicit agrees (via a different spelling) -> ok
        p, src = resolve_corpus_dir(str(full / '..' / 'full'), read_meta(man), man, 'T')
        check('stamped + agreeing explicit (different spelling) -> ok', 'agrees' in src, src)

        # 5. stamped, explicit DISAGREES -> REFUSE naming both (the drift case)
        try:
            resolve_corpus_dir(str(video), read_meta(man), man, 'T'); check('drift refused', False)
        except CorpusDirError as e:
            check('stamped + disagreeing explicit -> REFUSES naming both paths',
                  'full' in str(e) and 'video' in str(e) and 'drift' in str(e), str(e))

        # 6. stamped with a dir that does not exist here -> REFUSE, names re-stamp
        man.write_text(json.dumps({'_meta': {META_KEY: '/nonexistent/x'}}) + '\n')
        try:
            resolve_corpus_dir(None, read_meta(man), man, 'T'); check('missing dir refused', False)
        except CorpusDirError as e:
            check('stamped dir absent on this layout -> REFUSES, names re-stamp',
                  '/nonexistent/x' in str(e) and 'stamp' in str(e), str(e))

        # 7. unreadable/absent manifest -> empty meta, not a crash
        check('absent manifest -> empty meta', read_meta(d / 'nope.jsonl') == {})
        (d / 'bad.jsonl').write_text('{not json')
        check('unparseable manifest -> empty meta', read_meta(d / 'bad.jsonl') == {})

        # 8. NULL CONTROL: the class is a SystemExit with rc 1 and a NOT DONE message
        try:
            raise CorpusDirError('x')
        except SystemExit as e:
            check('CorpusDirError exits 1 with NOT DONE', str(e).startswith('NOT DONE') and e.code == 'NOT DONE — x')

    print(f'\ncorpus_locator self-test: {"PASS" if not fails else "FAIL"} ({len(fails)} failing)')
    return 1 if fails else 0


def main() -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False, description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--manifest', required=False, default=None)
    ap.add_argument('--corpus-dir', default=None, help='explicit; must agree with the meta')
    ap.add_argument('--self-test', action='store_true')
    ap.add_argument('--tool', default='run_plan')
    args = ap.parse_args()
    if args.self_test:
        return _self_test()
    if not args.manifest:
        print('NOT DONE — --manifest is required'); return 1
    man = Path(args.manifest)
    if not man.is_file():
        print(f'NOT DONE — manifest {man} is not a file'); return 1
    try:
        p, src = resolve_corpus_dir(args.corpus_dir, read_meta(man), man, args.tool)
    except CorpusDirError as e:
        print(str(e)); return 1
    # stdout line 1 = the path, line 2 = where it came from. run_plan splits them;
    # the source is LOGGED, not only the value — a path nobody can see the origin
    # of is how a wrong default survived three tools.
    print(p)
    print(src)
    return 0


if __name__ == '__main__':
    sys.exit(main())
