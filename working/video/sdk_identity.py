#!/usr/bin/env python3
"""SDK identity read-back — instance six of the environment-identity class.

THE INCIDENT (2026-08-22): every video-tree file imported `RocketRide`, a class
that exists in NO generation of the SDK surface — not the installed wheel, not
the docs, not the dev checkout. Eight sites across six files, perfectly
self-consistent, none executed: consistency across one author's output had been
read as evidence. The bake died on the first import ever attempted. The fix
template was Phase 1's measured usage (40+ sites of `RocketRideClient`, bare
constructor, env-resolved credentials), confirmed against the installed wheel's
own inspect.signature output (box paste, 2026-08-22).

What this module keeps true from now on:

* readback(): the installed SDK exposes every entry point the video tree
  calls — NAMES and PARAMETERS. A renamed kwarg is invisible to getattr;
  inspect.signature sees it. An SDK bump therefore fails at preflight, not
  mid-leg. Null-controlled on every invocation: the checker must first FLAG a
  fabricated method and a fabricated parameter, or it refuses itself.

* scan_tree(): the static breaker for the self-consistency failure mode.
  Every `from rocketride import X` and every `client.<method>(` in the tree
  must be inside the verified surface below. Pure text — runs on the laptop
  with no SDK installed (Crossroad 20 scope) and again at bake stage 0, i.e.
  BEFORE first execution. Agreement between N copies of one memory is one
  observation; agreement with this list is a measurement. A legitimate new
  SDK call fails the scan until REQUIRED_METHOD_PARAMS is extended WITH ITS
  EVIDENCE — that friction is the point.

* assert_unique_project_ids(): D3's property, kept true per run. The engine
  derives the task token from (userId, project_id, source) when none is given
  (task_server.py:1074, pinned 3.3.1 source), so two live tasks sharing a
  project_id either collide loudly ('Pipeline is already running.') or — under
  use_existing — silently share ONE task: a parity posture measuring a queue.
  The thing that made D3 invisible was that nothing ever looked.

Importing this module needs stdlib only (rocketride imports lazily inside
readback), so make_sample_export and laptop syntax checks stay SDK-free. Runs
under either venv contract (~/.venv or ~/.venv-floor; both pin
rocketride==1.3.0, export lists measured identical 2026-08-22).
"""
from __future__ import annotations

import argparse
import inspect
import json
import re
import sys
from pathlib import Path

# The measured surface. Evidence, in order of authority:
#   1. installed wheel, box, 2026-08-22: inspect.signature paste for these
#      five methods; export list contains RocketRideClient (never `RocketRide`);
#   2. Phase 1 usage: 40+ sites `from rocketride import RocketRideClient`.
# Parameters listed are the ones the video tree actually passes. The wheel's
# use() also carries `team_id`, which the dev checkout lacks — proof that
# checkout != wheel, and why only measured surfaces belong here.
REQUIRED_IMPORT = 'RocketRideClient'
REQUIRED_METHOD_PARAMS: dict[str, set] = {
    'connect': {'timeout'},
    'use': {'filepath', 'ttl', 'threads'},
    'send': {'token', 'data', 'objinfo', 'mimetype'},
    'terminate': {'token'},
    'disconnect': set(),
}


def _missing(cls, spec: dict) -> list[str]:
    problems = []
    for meth, params in spec.items():
        fn = getattr(cls, meth, None)
        if fn is None:
            problems.append(f'method {meth!r} ABSENT')
            continue
        try:
            have = set(inspect.signature(fn).parameters)
        except (TypeError, ValueError):
            problems.append(f'method {meth!r}: signature unreadable')
            continue
        gone = set(params) - have
        if gone:
            problems.append(f'method {meth!r}: parameters missing {sorted(gone)}')
    return problems


def readback(strict: bool = True) -> dict:
    """Version + module path + entry-point verification against the INSTALLED SDK.

    strict=True (the only mode a measured path may use) raises RuntimeError
    naming exactly what is missing. The report lands in preflight.json, the
    export's provenance, the smoke, and the bake read-back.
    """
    try:
        import rocketride
    except ImportError as exc:
        if strict:
            raise RuntimeError(
                'NOT DONE — SDK identity: rocketride is not importable in this '
                f'interpreter ({sys.executable}). The video tree runs under a venv '
                'with rocketride==1.3.0 (both ~/.venv and ~/.venv-floor).') from exc
        return {'ok': False, 'error': f'rocketride not importable: {exc}',
                'python_executable': sys.executable}
    try:
        from importlib.metadata import version
        pkg_version = version('rocketride')
    except Exception:  # noqa: BLE001 — metadata absent is reportable, not fatal
        pkg_version = getattr(rocketride, '__version__', '?')
    report: dict = {
        'package_version': pkg_version,
        'module_path': rocketride.__file__,
        'python_executable': sys.executable,
        'python_version': sys.version.split()[0],
        'verified_surface': {m: sorted(p) for m, p in REQUIRED_METHOD_PARAMS.items()},
    }
    cls = getattr(rocketride, REQUIRED_IMPORT, None)
    if cls is not None:
        # NULL CONTROL first — a checker that cannot flag a known-bad proves
        # nothing when it passes the real list.
        null_hits = (_missing(cls, {'definitely_absent_method_xq': set()})
                     + _missing(cls, {'send': {'definitely_absent_param_xq'}}))
        if len(null_hits) != 2:
            raise RuntimeError('NOT DONE — sdk_identity NULL CONTROL failed to fire '
                               f'({null_hits!r}); the checker itself is broken.')
        report['null_control'] = 'fired (2/2)'
    problems = [] if cls is not None else [f'{REQUIRED_IMPORT!r} ABSENT from rocketride']
    if cls is not None:
        problems += _missing(cls, REQUIRED_METHOD_PARAMS)
    report['ok'] = not problems
    report['problems'] = problems or None
    if problems and strict:
        raise RuntimeError(
            f'NOT DONE — SDK surface mismatch (rocketride {pkg_version} at '
            f'{rocketride.__file__}): ' + '; '.join(problems))
    return report


# ---------------------------------------------------------------------------
# Static scan — catches the incident's failure mode before first execution
# ---------------------------------------------------------------------------
_IMPORT_RE = re.compile(r'^\s*from\s+rocketride\s+import\s+(.+?)\s*$', re.M)
_CALL_RE = re.compile(r'\b(?:self\.)?client\.([a-z_]+)\(')


def _scan_text(text: str, label: str) -> list[str]:
    problems = []
    for m in _IMPORT_RE.finditer(text):
        for name in (n.strip() for n in m.group(1).split(',')):
            if name and name != REQUIRED_IMPORT:
                problems.append(f'{label}: imports {name!r} from rocketride — not in the '
                                f'verified surface (only {REQUIRED_IMPORT!r} is)')
    for m in _CALL_RE.finditer(text):
        if m.group(1) not in REQUIRED_METHOD_PARAMS:
            problems.append(f'{label}: calls client.{m.group(1)}() — not in the verified '
                            'surface; extend REQUIRED_METHOD_PARAMS with evidence first')
    return problems


def scan_tree(root: Path) -> dict:
    """Scan .py and .sh (heredocs included) under root. SDK-free, laptop-safe."""
    # Built-in null control: the matchers must flag a known-bad snippet.
    null = _scan_text('from rocketride import TotallyWrongName\nclient.fabricated_method(x)\n',
                      '<null>')
    if len(null) != 2:
        raise RuntimeError(f'NOT DONE — scan NULL CONTROL failed to fire ({null!r})')
    problems, files = [], 0
    me = Path(__file__).resolve()
    for p in sorted(root.rglob('*')):
        if p.suffix not in ('.py', '.sh') or '__pycache__' in p.parts:
            continue
        if p.resolve() == me:
            continue
        files += 1
        problems += _scan_text(p.read_text(errors='replace'), p.name)
    return {'ok': not problems, 'files_scanned': files,
            'null_control': 'fired (2/2)', 'problems': problems or None}


# ---------------------------------------------------------------------------
# D3's standing property
# ---------------------------------------------------------------------------
def assert_unique_project_ids(pairs) -> dict:
    """pairs: iterable of (label, project_id) for tasks live AT THE SAME TIME.
    One function, fed by the driver and both RR probes."""
    seen: dict = {}
    dupes = []
    for label, pid in pairs:
        if pid in seen:
            dupes.append((seen[pid], label, pid))
        else:
            seen[pid] = label
    if dupes:
        raise RuntimeError(
            f'NOT DONE — project_id shared between concurrent tasks: {dupes}. The '
            'engine derives the task token from (userId, project_id, source) '
            "(task_server.py:1074) — a shared id is a collision ('Pipeline is "
            "already running.') or a silent shared task (D3).")
    return {'n_tasks': len(seen), 'unique': True}


def main() -> int:
    ap = argparse.ArgumentParser(
        description='SDK identity read-back + static surface scan (instance six).')
    ap.add_argument('--json', action='store_true', help='print the full read-back as JSON')
    ap.add_argument('--scan', nargs='?', const=str(Path(__file__).resolve().parent),
                    default=None, metavar='DIR',
                    help='static scan of DIR (default: working/video) — needs no SDK')
    args = ap.parse_args()
    if args.scan:
        rep = scan_tree(Path(args.scan))
        print(json.dumps(rep, indent=1))
        return 0 if rep['ok'] else 1
    try:
        rep = readback(strict=True)
    except RuntimeError as exc:
        print(exc)
        return 1
    print(json.dumps(rep, indent=1) if args.json else
          f"SDK OK — rocketride {rep['package_version']} at {rep['module_path']} "
          f"(entry points verified, null control fired)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
