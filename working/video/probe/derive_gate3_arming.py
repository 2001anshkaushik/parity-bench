#!/usr/bin/env python3
"""RULINGS Q + R (2026-08-31): films gate-3 arming + LIVENESS_MIN derivation.

Consumes the two staged sequential records (one film, BOTH arms, produced by
the leg driver itself so the arming measures the real pipeline) and:

  Q — runs gate 3 STRICT (gates_shared.label_multiset_agreement, threshold
      0.3 / boundary_eps 0.001 — the committed gate, not a re-implementation)
      on the staged film's per-frame label multisets. PASS -> writes the
      arming artifact whose id becomes GATE3_RUN_ID. FAIL -> writes
      arming_FAILED_<utc>.json with the full diagnosis (diverging frames +
      score_triage) and exits 1 — a films cross-arm divergence is a STOP
      finding, never something to arm past. The same-frames precondition for
      the staged film is the committed byte-level parity evidence
      (probe_frame_parity_20000LeaguesUndertheSea.json, A==B==C EXACT).

  R — cuts LIVENESS_MIN FROM this run, never from Corner: per-arm
      non-empty-frame fraction from the records' own frame_labels;
      liveness_min = round(0.5 * min(fractions), 3) — the measured minimum
      with a stated 2x margin, derivation recorded verbatim in the artifact
      (single-film basis DISCLOSED; re-ruling from full-leg data is cheap
      later). If the records cannot supply fractions, the artifact says
      liveness_min: null with the reason — the run plan then runs gate 5
      NOT RUN, never a guessed number.

Exit 0 = armed + artifact written / 1 = refusal (evidence artifact written)
/ 4 = self-test failure.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # working/video
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # working/
from harness import gates_shared as gs   # noqa: E402 — the committed gate

UTC = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())


def first_measured(records_path: Path) -> dict:
    """First non-error, non-repeat record — the staged film."""
    rows = [json.loads(l) for l in records_path.read_text().splitlines()
            if l.strip()]
    ok = [r for r in rows if 'error' not in r
          and '::repeat' not in str(r.get('video'))]
    if not ok:
        raise SystemExit(f'NOT DONE — no usable record in {records_path}')
    return ok[0]


def nonempty_fraction(frame_labels) -> float:
    if not frame_labels:
        raise SystemExit('NOT DONE — record carries no frame_labels; '
                         'liveness cannot be derived from nothing')
    return sum(1 for f in frame_labels if f) / len(frame_labels)


def derive(rr: dict, li: dict, git_head: str) -> dict:
    if rr.get('video') != li.get('video'):
        raise SystemExit(f"NOT DONE — different films: rr={rr.get('video')!r} "
                         f"li={li.get('video')!r}; arming needs ONE staged film "
                         'on both arms (entry 14: same-input or CANNOT COMPARE)')
    agreement = gs.label_multiset_agreement(
        rr.get('frame_labels') or [], li.get('frame_labels') or [],
        rr.get('frame_scores'), li.get('frame_scores'),
        threshold=0.3, boundary_eps=0.001)
    fr_rr = nonempty_fraction(rr.get('frame_labels'))
    fr_li = nonempty_fraction(li.get('frame_labels'))
    liveness_min = round(0.5 * min(fr_rr, fr_li), 3)
    return {
        'probe': 'derive_gate3_arming', 'created_utc': UTC,
        'git_head': git_head,
        'gate3_run_id': f'films-staging-{UTC}-{git_head[:8]}',
        'film': rr.get('video'),
        'film_choice_reason': (
            'first measured manifest row (deterministic; what --n 1 sends) '
            'AND the film whose frames are proven byte-identical A==B==C '
            'across the engine argv / LI pipe / LI file paths — committed '
            'probe_frame_parity artifact — so the same-frames precondition '
            'is strongest exactly here'),
        'agreement': agreement,
        'liveness': {
            'nonempty_frame_fraction_rr': round(fr_rr, 4),
            'nonempty_frame_fraction_li': round(fr_li, 4),
            'liveness_min': liveness_min,
            'derivation': ('RULING R: 0.5 x min(per-arm non-empty-frame '
                           'fraction) measured on the staged film by the leg '
                           "driver's own records — the measured minimum with "
                           'a stated 2x margin. Single-film basis DISCLOSED; '
                           'never a Corner-derived number on films content.'),
        },
        'armed': agreement.get('PASS') is True,
    }


def self_test() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f'  {"PASS" if cond else "FAIL"}  {name}')
        ok = ok and cond

    agree_rr = {'video': 'f.mp4', 'frame_labels': [['a'], [], ['b', 'b']],
                'frame_scores': [[0.9], [], [0.8, 0.7]]}
    agree_li = json.loads(json.dumps(agree_rr))
    art = derive(agree_rr, agree_li, 'deadbeefcafe')
    check('agreeing film arms (strict gate PASS, armed true)',
          art['armed'] is True and art['agreement']['PASS'] is True)
    check('liveness = 0.5 x min fraction (2/3 frames non-empty -> 0.333)',
          art['liveness']['liveness_min'] == 0.333
          and art['liveness']['nonempty_frame_fraction_rr'] == 0.6667)
    check('run id carries utc + head', 'deadbeef' in art['gate3_run_id'])
    dis_li = json.loads(json.dumps(agree_rr))
    dis_li['frame_labels'][2] = ['b']          # real divergence, far from eps
    dis_li['frame_scores'][2] = [0.8]
    art2 = derive(agree_rr, dis_li, 'deadbeefcafe')
    check('diverging arms -> armed false, gate FAIL (null control fires)',
          art2['armed'] is False and art2['agreement']['PASS'] is False
          and art2['agreement']['n_diverging'] == 1)
    try:
        derive(agree_rr, {'video': 'other.mp4', 'frame_labels': [['a']]},
               'deadbeefcafe')
        check('different films REFUSED (same-input or CANNOT COMPARE)', False)
    except SystemExit as e:
        check('different films REFUSED (same-input or CANNOT COMPARE)',
              'CANNOT COMPARE' in str(e))
    try:
        nonempty_fraction([])
        check('empty frame_labels refused, never a derived zero', False)
    except SystemExit as e:
        check('empty frame_labels refused, never a derived zero',
              'nothing' in str(e))

    # ENTRY 27: every probe self-test scans the video tree for unresolvable
    # names. Lazy import: live paths untouched.
    from harness.static_names import probe_selftest_findings
    sn = probe_selftest_findings(__file__)
    check('static names: every video-tree name resolves (entry 27)', sn == {})
    if sn:
        print('  UNRESOLVED:', sn)

    print('self-test:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 4


def main() -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--rr-records')
    ap.add_argument('--li-records')
    ap.add_argument('--out', default=str(Path.home() / 'films_probe'
                                         / 'gate3_films' / 'arming.json'))
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not args.rr_records or not args.li_records:
        ap.error('--rr-records and --li-records are required')
    repo = Path(__file__).resolve().parents[3]
    head = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'],
                          capture_output=True, text=True).stdout.strip()
    rr = first_measured(Path(args.rr_records).expanduser())
    li = first_measured(Path(args.li_records).expanduser())
    art = derive(rr, li, head)
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    if not art['armed']:
        fail_path = out.parent / f'arming_FAILED_{UTC}.json'
        art['score_triage'] = gs.score_triage(rr.get('frame_scores') or [],
                                              li.get('frame_scores') or [])
        fail_path.write_text(json.dumps(art, indent=1))
        print(f'NOT DONE — gate 3 STRICT FAILED on the staged film '
              f"{art['film']}: {json.dumps(art['agreement'])[:400]} — a "
              f'films cross-arm divergence is a STOP finding; evidence at '
              f'{fail_path}. NOTHING IS ARMED.')
        return 1
    out.write_text(json.dumps(art, indent=1))
    rb = json.loads(out.read_text())          # entry 22: read back
    print(f"ARMED: gate3_run_id={rb['gate3_run_id']} film={rb['film']} "
          f"boundary_excluded={rb['agreement'].get('n_boundary_excluded')} "
          f"liveness_min={rb['liveness']['liveness_min']} "
          f"(fractions rr={rb['liveness']['nonempty_frame_fraction_rr']} "
          f"li={rb['liveness']['nonempty_frame_fraction_li']}) -> {out}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
