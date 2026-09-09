#!/usr/bin/env python3
"""Re-count the comparison arm's LOC at the CURRENT tree, under the chart rule.

Why this exists beside `count_loc_video.py` (whose output is banked in
`loc_report_video.json`, measured 2026-08-26 at commit 6ce2f9c):

  1. RULE. The chart's stated rule is non-blank, non-comment code lines,
     EXCLUDING Dockerfiles and requirements, broken down by layer. The M6
     report's three totals (387 / 300 / 283) all INCLUDE the Dockerfile, and
     the M6 `layers.serving_integration` (172) carries the Dockerfile's 85
     inside it. Neither number can go on the chart as-is.
  2. TREE. M6 predates the LI streaming refactor (`b295dea`, 2026-08-27,
     which rewrote pipeline.py and service.py) and Ruling L (`6143aab`,
     2026-08-29). The banked figures describe a service that no longer exists.

The COUNTER IS NOT NEW: this imports `count_loc_video`'s own `classify`,
`pipe_formatting` and `semantic_units` unmodified — the same line rules, the
same instrumentation/ambiguous knife, the same four layers. The only changes
are the file set (Dockerfile and the 149-pin freeze excluded by the chart rule)
and the output path (a NEW artifact; the M6 artifacts are never overwritten).

Run:  python3 working/video/loc/recount_loc_head.py [--rev COMMIT] [--out out.json]

--rev counts a HISTORICAL tree, which is what an era-scoped figure needs: the AMI
campaign ran two different trees, and the number that describes a campaign is the
one measured on the tree that campaign actually ran. Files are materialised with
`git show <rev>:<path>`, so nothing in the working tree is touched, and a file
absent at that rev is reported as absent rather than counted as zero.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'working' / 'video' / 'loc'))
import count_loc_video as M                             # noqa: E402 — committed tool, unmodified

V = ROOT / 'working' / 'video'
COUNTED = [V / 'li_video' / n for n in ('service.py', 'pipeline.py', 'schema.py', '__init__.py')]
# Present in the arm's source tree, NOT counted, each with the reason:
EXCLUDED = {
    'docker/Dockerfile.llamaindex-video': 'Dockerfile — excluded by the chart rule',
    'working/video/li_video/li_image_freeze.txt': 'requirements (149 pins) — excluded by the chart rule',
    'working/video/li_video/extract_engine_pins.sh': 'build-time provenance tooling — outside the M6 scope '
                                                     'ruling (harness/driver/gates/collector/probes excluded)',
}
LAYER_OF = {'pipeline.py': 'compute_transforms', 'service.py': 'serving_integration',
            'schema.py': 'serving_integration', '__init__.py': 'serving_integration'}
BANKED = {  # loc_report_video.json, committed at 6ce2f9c (2026-08-26)
    'service.py': (73, 35, 5), 'pipeline.py': (111, 27, 7), 'schema.py': (14, 25, 5), '__init__.py': (0, 0, 0),
}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def blob(rev: str | None, rel: str, tmp: Path) -> Path | None:
    """The file as of `rev`, materialised under `tmp` keeping its basename (the
    counter's docstring handling keys off the .py suffix). None if absent there."""
    if rev is None:
        f = ROOT / rel
        return f if f.exists() else None
    r = subprocess.run(['git', '-C', str(ROOT), 'show', f'{rev}:{rel}'],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    out = tmp / Path(rel).name
    out.write_text(r.stdout)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--rev', default=None, help='count this commit instead of the working tree')
    ap.add_argument('--out', default=None)
    ap.add_argument('positional_out', nargs='?', default=None, help=argparse.SUPPRESS)
    a = ap.parse_args()
    rev = a.rev
    tmp = Path(tempfile.mkdtemp(prefix='loc_rev_'))

    per, layers, absent, srcs = {}, {}, [], []
    for f in COUNTED:
        rel = str(f.relative_to(ROOT))
        src = blob(rev, rel, tmp)
        if src is None:
            absent.append(rel)
            continue
        srcs.append(src)
        c, _rows = M.classify(src)
        b = BANKED[f.name]
        per[rel] = {
            'service': c['service'], 'instrumentation': c['instrumentation'], 'ambiguous': c['ambiguous'],
            'all_classes': sum(c.values()), 'raw_lines': len(src.read_text().splitlines()),
            'layer': LAYER_OF[f.name], 'sha256': sha(src),
            'banked_m6': {'service': b[0], 'instrumentation': b[1], 'ambiguous': b[2], 'all_classes': sum(b)},
            'delta_service': c['service'] - b[0], 'delta_all_classes': sum(c.values()) - sum(b),
        }
    tot = {k: sum(v[k] for v in per.values()) for k in ('service', 'instrumentation', 'ambiguous', 'all_classes')}
    bank_tot = {k: sum(v['banked_m6'][k] for v in per.values())
                for k in ('service', 'instrumentation', 'ambiguous', 'all_classes')}
    for key, name in (('service', 'service_only'), ('all_classes', 'all_classes')):
        layers[name] = {'pipeline_definition': 0, 'client_harness': 0,
                        'compute_transforms': sum(v[key] for v in per.values() if v['layer'] == 'compute_transforms'),
                        'serving_integration': sum(v[key] for v in per.values() if v['layer'] == 'serving_integration')}
    head = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', rev or 'HEAD'],
                          capture_output=True, text=True, check=True).stdout.strip()
    when = subprocess.run(['git', '-C', str(ROOT), 'log', '-1', '--format=%ad', '--date=iso-strict', head],
                          capture_output=True, text=True, check=True).stdout.strip()
    report = {
        'measured_at_commit': head, 'commit_date': when,
        'tree': ('working tree' if rev is None else f'historical tree at {rev}'),
        'files_absent_at_this_rev': absent,
        'rule': 'non-blank, non-comment code lines (docstrings excluded); Dockerfiles and requirements EXCLUDED; '
                'four COUNTING_RULE layers',
        'counter': f'count_loc_video.classify (committed, unmodified); METHOD A for reference: {M.COUNTER_SRC}',
        'scope_ruling': 'developer-written service only; harness/driver/gates/collector/probes excluded '
                        '(operator 2026-08-26)',
        'supersedes_for_this_rule': 'loc_report_video.json (M6, commit 6ce2f9c, 2026-08-26) — same counter, '
                                    'different file set (Dockerfile included there) and an older tree '
                                    '(pre b295dea streaming refactor, pre 6143aab Ruling L)',
        'llamaindex': {'per_file': per, 'totals': tot, 'banked_m6_totals': bank_tot,
                       'delta_vs_m6': {k: tot[k] - bank_tot[k] for k in tot}, 'layers': layers},
        'excluded_files': {},
        'rocketride': {'pipeline_definition_formatting_spread': M.pipe_formatting(V / 'benchmark_video_detect.pipe'),
                       'compute_transforms': 0, 'serving_integration': 0, 'client_harness': 0,
                       'note': 'engine-internal stages are product code, not user code (COUNTING_RULE §2); no '
                               'developer-written service and no authored Dockerfile for this pipeline'},
        'semantic_units': {},   # filled below from the SAME tree
    }
    for k, v in EXCLUDED.items():
        src = blob(rev, k, tmp)
        report['excluded_files'][k] = ({'reason': v, 'absent_at_this_rev': True} if src is None else
                                       {'reason': v, 'lines': len(src.read_text().splitlines()),
                                        'loc_method_a': (M.count_loc(src) if 'Dockerfile' in k else None),
                                        'sha256': sha(src)})
    pipe_src = blob(rev, 'working/video/benchmark_video_detect.pipe', tmp) or (V / 'benchmark_video_detect.pipe')
    report['rocketride']['pipeline_definition_formatting_spread'] = M.pipe_formatting(pipe_src)
    report['semantic_units'] = {'llamaindex': M.semantic_units(srcs, None),
                                'rocketride': M.semantic_units([], pipe_src)}
    out = Path(a.out or a.positional_out or (Path(__file__).parent / 'loc_report_video_HEAD.json'))
    out.write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps({'measured_at_commit': head, 'commit_date': when, 'tree': report['tree'],
                      'totals': tot, 'delta_vs_m6': report['llamaindex']['delta_vs_m6'], 'layers': layers,
                      'excluded_files': {k: (v.get('lines'), v.get('loc_method_a'), v.get('absent_at_this_rev'))
                                         for k, v in report['excluded_files'].items()},
                      'files_absent_at_this_rev': absent}, indent=1))
    print(f'written: {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
