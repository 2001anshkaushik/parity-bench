#!/usr/bin/env python3
"""Validated argparse types — register entry 8 (2026-08-21).

THE CLASS: a required-argument guard that checks PRESENCE rather than
PLAUSIBILITY cannot fail for the case it was built for. The video tree's
probe-derived arguments refused to *default*, but nothing bounded what a
present flag could carry: a float argument would accept 2595.0 as readily as
25.95, and argparse's prefix abbreviation would silently accept
`--measured-chars` for `--measured-chars-per-det`. Kin to "a command that
warns and exits zero" (register entry 4 companion): both are failures wearing
a success's clothes — one at the shell, one at the argument parser.

Every type here validates the PARSED VALUE:
  * a value containing '--' is rejected naming the missing-space hypothesis
    (the reported incident shape: `25.95--measured-chars-per-det`);
  * numeric values must sit inside a stated plausibility range — the bounds
    are wide envelopes around measured reality, not guesses at it, and the
    error names value, bound, and argument;
  * run ids must not look like flags.

Callers also pass allow_abbrev=False to ArgumentParser — an abbreviated flag
is an unmeasured claim of identity.

Stdlib only; importable from working/video and working/video/probe alike.
Run this file directly to execute its null-controlled self-test.
"""
from __future__ import annotations

import sys
from argparse import ArgumentTypeError


def _no_double_dash(name: str, s: str) -> None:
    if '--' in s:
        raise ArgumentTypeError(
            f'{name}: value {s!r} contains "--" — missing space between '
            'arguments? (each flag and each value must be its own shell word)')


def bounded_float(name: str, lo: float, hi: float):
    """Float in [lo, hi]; rejects '--'-bearing strings with the missing-space
    hypothesis and out-of-range values by name."""
    def parse(s: str) -> float:
        _no_double_dash(name, s)
        try:
            v = float(s)
        except ValueError:
            raise ArgumentTypeError(f'{name}: {s!r} is not a number')
        if not (lo <= v <= hi):
            raise ArgumentTypeError(
                f'{name}: {v} outside the plausibility range [{lo}, {hi}] — '
                'if the true measured value really sits outside it, widen the '
                'bound HERE with the evidence, never by silencing the check')
        return v
    parse.__name__ = f'bounded_float[{lo},{hi}]'
    return parse


def positive_int(name: str, hi: int = 1_000_000):
    """Integer in [1, hi]; same '--' and range discipline."""
    def parse(s: str) -> int:
        _no_double_dash(name, s)
        try:
            v = int(s)
        except ValueError:
            raise ArgumentTypeError(f'{name}: {s!r} is not an integer')
        if not (1 <= v <= hi):
            raise ArgumentTypeError(f'{name}: {v} outside [1, {hi}]')
        return v
    parse.__name__ = f'positive_int[1,{hi}]'
    return parse


def run_id(name: str):
    """Identifier: non-empty, not flag-shaped, no '--' inside."""
    def parse(s: str) -> str:
        _no_double_dash(name, s)
        if not s or s.startswith('-'):
            raise ArgumentTypeError(f'{name}: {s!r} looks like a flag, not an id')
        return s
    parse.__name__ = 'run_id'
    return parse


def _self_test() -> int:
    """Null-controlled: every rejection path MUST fire; every good value must pass."""
    cases_bad = [
        (bounded_float('x', 0.1, 500), '25.95--measured-chars-per-det'),  # the incident shape
        (bounded_float('x', 0.1, 500), 'banana'),
        (bounded_float('x', 0.1, 500), '2595.0'),          # plausible-typo, implausible value
        (positive_int('x', 64), '0'),
        (positive_int('x', 64), '65'),
        (positive_int('x', 64), '8x'),
        (run_id('x'), '--arm'),
        (run_id('x'), 'a--b'),
    ]
    cases_good = [
        (bounded_float('x', 0.1, 500), '25.95', 25.95),
        (positive_int('x', 64), '8', 8),
        (run_id('x'), 'probe_20260821_195214', 'probe_20260821_195214'),
    ]
    failures = []
    for fn, raw in cases_bad:
        try:
            fn(raw)
            failures.append(f'NULL CONTROL FAILED to fire: {fn.__name__}({raw!r})')
        except ArgumentTypeError:
            pass
    for fn, raw, want in cases_good:
        try:
            got = fn(raw)
            if got != want:
                failures.append(f'{fn.__name__}({raw!r}) == {got!r}, wanted {want!r}')
        except ArgumentTypeError as exc:
            failures.append(f'{fn.__name__}({raw!r}) wrongly rejected: {exc}')
    for f in failures:
        print(f'FAIL {f}')
    print(f'argtypes self-test: {len(cases_bad)} rejections fired, '
          f'{len(cases_good)} good values passed' if not failures else
          f'argtypes self-test: {len(failures)} FAILURES')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(_self_test())
