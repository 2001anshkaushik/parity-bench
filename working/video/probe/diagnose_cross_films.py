#!/usr/bin/env python3
"""Cross-gate failure diagnosis (2026-09-01) — READ-ONLY over the completed
campaign's records and cross files. Changes no gate, re-runs nothing.

Context: the films main run banked 9 legs / 0 errors / per-leg gates green,
and cross_detection_agreement FAILED on 34 of 35 films in every cell — the
ONE passing film (20000LeaguesUndertheSea, 395/395, n_diverging 0, every
cell) is exactly the arming film and the only measured film ever proven
byte-identical A==B==C by probe_frame_parity. Hypothesis under test: the
arms decoded DIFFERENT FRAMES on the unverified films (same count — gate 1
passed both arms — different content, VFR selection), in which case those
films' gate-3 verdict is CANNOT COMPARE (entry 14), not FAIL.

This tool prints, from the artifacts already on disk:
  TASK 2 — for one film: per-frame divergence anatomy (count-mismatch vs
    same-count-different-content split; which arm detects MORE, per frame
    and in total; divergence rate by frame-index quartile; longest clean
    prefix; the first N diverging frames side by side with scores) — a
    drift-with-index pattern is the VFR-selection signature, a flat random
    pattern points downstream.
  TASK 4 — char_conservation ratio distribution per cell (band-cutting DATA
    per Ruling T, never a headline), the per-film join of char ratio vs
    n_diverging and vs the arms' detection-count ratio (the confound path:
    different detections -> different detect-JSON volume -> different char
    sums), and the LI embed-stage share (bounds the throughput confound).

Field access rides the ONE producer-named accessor (derive_gate3_arming.
gate3_inputs) and the self-test builds every fixture through the REAL
producers (driver_video.record_from_li -> jsonl -> driver_video.cross_gates)
— entry 27's addenda, applied at write time.

Exit 0 diagnosis printed / 1 refusal / 4 self-test failure.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # working/video
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # working/
sys.path.insert(0, str(Path(__file__).resolve().parent))       # probe/
from derive_gate3_arming import gate3_inputs   # noqa: E402 — one accessor


def load_records(path: Path) -> dict:
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    return {r['video']: r for r in rows
            if 'error' not in r and '::repeat' not in str(r.get('video'))}


def frame_anatomy(rr_rec: dict, li_rec: dict, dump_n: int = 6) -> dict:
    """Per-frame divergence anatomy for one film, both arms."""
    rr_labels, rr_scores = gate3_inputs(rr_rec)
    li_labels, li_scores = gate3_inputs(li_rec)
    if len(rr_labels) != len(li_labels):
        return {'verdict': 'FRAME COUNT DIFFERS',
                'rr': len(rr_labels), 'li': len(li_labels)}
    n = len(rr_labels)
    div = [i for i in range(n) if sorted(rr_labels[i]) != sorted(li_labels[i])]
    count_mismatch = [i for i in div if len(rr_labels[i]) != len(li_labels[i])]
    rr_more = sum(1 for i in count_mismatch
                  if len(rr_labels[i]) > len(li_labels[i]))
    quarters = [0, 0, 0, 0]
    qsize = [0, 0, 0, 0]
    for i in range(n):
        q = min(3, i * 4 // n)
        qsize[q] += 1
        if sorted(rr_labels[i]) != sorted(li_labels[i]):
            quarters[q] += 1
    clean_prefix = div[0] if div else n
    dump = []
    for i in div[:dump_n]:
        dump.append({
            'frame': i,
            'rr': {'labels': rr_labels[i],
                   'scores': [round(float(s), 3) for s in (rr_scores or [[]] * n)[i]]},
            'li': {'labels': li_labels[i],
                   'scores': [round(float(s), 3) for s in (li_scores or [[]] * n)[i]]},
        })
    return {
        'n_frames': n,
        'n_diverging': len(div),
        'diverging_fraction': round(len(div) / n, 3) if n else None,
        'split': {'count_mismatch': len(count_mismatch),
                  'same_count_different_content': len(div) - len(count_mismatch)},
        'direction': {'rr_more_detections': rr_more,
                      'li_more_detections': len(count_mismatch) - rr_more,
                      'film_n_detections_rr': rr_rec.get('n_detections')
                      or sum(len(f) for f in rr_labels),
                      'film_n_detections_li': li_rec.get('n_detections')
                      or sum(len(f) for f in li_labels)},
        'index_pattern': {
            'first_diverging_frame': div[0] if div else None,
            'longest_clean_prefix': clean_prefix,
            'diverging_rate_by_quartile': [
                round(quarters[q] / qsize[q], 3) if qsize[q] else None
                for q in range(4)],
            'note': 'a rate that GROWS with index = timestamp-drift '
                    '(VFR frame-selection) signature; flat = downstream',
        },
        'first_diverging_frames': dump,
    }


def corpus_direction(rr_by: dict, li_by: dict) -> dict:
    """Across every paired film: who detects more, and by how much."""
    rows = []
    for v in sorted(set(rr_by) & set(li_by)):
        rl, _ = gate3_inputs(rr_by[v])
        ll, _ = gate3_inputs(li_by[v])
        nr = rr_by[v].get('n_detections') or sum(len(f) for f in rl)
        nl = li_by[v].get('n_detections') or sum(len(f) for f in ll)
        rows.append({'video': v, 'n_det_rr': nr, 'n_det_li': nl,
                     'det_ratio_rr_over_li': round(nr / nl, 4) if nl else None})
    rr_more = sum(1 for r in rows if (r['n_det_rr'] or 0) > (r['n_det_li'] or 0))
    return {'n_films': len(rows), 'films_where_rr_detects_more': rr_more,
            'films_where_li_detects_more':
                sum(1 for r in rows if (r['n_det_li'] or 0) > (r['n_det_rr'] or 0)),
            'per_film': rows}


def char_band_data(cross: dict) -> dict:
    """char_conservation ratio distribution from ONE cross file — Ruling T:
    band-cutting DATA, never a headline verdict."""
    rows = (cross.get('char_conservation') or {}).get('rows') or []
    ratios = sorted(r['ratio_rr_over_li'] for r in rows
                    if r.get('ratio_rr_over_li') is not None)
    if not ratios:
        return {'n': 0, 'note': 'no ratio rows in this cross file'}
    mid = len(ratios) // 2
    med = (ratios[mid] if len(ratios) % 2 else
           round((ratios[mid - 1] + ratios[mid]) / 2, 4))
    return {'n': len(ratios), 'min': ratios[0], 'median': med,
            'max': ratios[-1],
            'inside_phase1_2pct': sum(1 for r in ratios if abs(r - 1) <= 0.02)}


def confound_join(cross: dict, rr_by: dict, li_by: dict) -> dict:
    """Per film: char ratio vs n_diverging vs detection-count ratio — the
    measured confound path (different detections -> different char sums)."""
    agr = (cross.get('cross_detection_agreement') or {}).get('per_video') or {}
    chars = {r['video']: r.get('ratio_rr_over_li')
             for r in (cross.get('char_conservation') or {}).get('rows') or []}
    rows = []
    for v, g in sorted(agr.items()):
        rr, li = rr_by.get(v), li_by.get(v)
        if not rr or not li:
            continue
        rl, _ = gate3_inputs(rr)
        nd = g.get('n_diverging') or 0
        nr = rr.get('n_detections') or 0
        nl = li.get('n_detections') or 0
        rows.append({'video': v, 'char_ratio': chars.get(v),
                     'n_diverging': nd,
                     'diverging_fraction': round(nd / len(rl), 3) if rl else None,
                     'det_ratio': round(nr / nl, 4) if nl else None,
                     'n_boundary_excluded': g.get('n_boundary_excluded')})
    with_r = [r for r in rows if r['char_ratio'] is not None
              and r['diverging_fraction'] is not None]
    with_r.sort(key=lambda r: r['diverging_fraction'])
    half = len(with_r) // 2
    def med(vals):
        s = sorted(vals)
        return (s[len(s) // 2] if len(s) % 2 else
                round((s[len(s) // 2 - 1] + s[len(s) // 2]) / 2, 4)) if s else None
    lo = med([abs(r['char_ratio'] - 1) for r in with_r[:half]])
    hi = med([abs(r['char_ratio'] - 1) for r in with_r[half:]])
    return {
        'per_film': rows,
        'confound_probe': {
            'median_char_ratio_low_divergence_half':
                round(lo, 4) if lo is not None else None,
            'median_char_ratio_high_divergence_half':
                round(hi, 4) if hi is not None else None,
            'note': 'if |ratio-1| is larger in the high-divergence half, the '
                    'char band is CONFOUNDED by the gate-3 problem and cannot '
                    'be cut from this run alone',
        },
    }


def li_embed_share(li_by: dict) -> dict:
    """Embed-stage share of LI wall — bounds how much of the throughput
    comparison the char-volume asymmetry can touch. RR records carry no
    stage_s (engine-side stages are not in the record shape) — stated."""
    tot = {'extract': 0.0, 'detect': 0.0, 'split': 0.0, 'embed': 0.0}
    n = 0
    for r in li_by.values():
        st = r.get('stage_s') or {}
        if st:
            n += 1
            for k in tot:
                tot[k] += float(st.get(k) or 0.0)
    s = sum(tot.values())
    return ({'n_records': n,
             'stage_share': {k: round(v / s, 4) for k, v in tot.items()},
             'note': 'embed share bounds the char-asymmetry confound on LI '
                     'wall; RR records carry no stage_s (n/a, stated)'}
            if s else {'n_records': n, 'note': 'no stage_s in records'})


def newest_results_dir(root: Path) -> Path:
    dirs = sorted(root.glob('films_mainrun_*'))
    if not dirs:
        raise SystemExit(f'NOT DONE — no films_mainrun_* under {root}')
    return dirs[-1]


def self_test() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f'  {"PASS" if cond else "FAIL"}  {name}')
        ok = ok and cond

    # Fixtures through the REAL producers: record_from_li -> jsonl ->
    # driver_video.cross_gates (entry 27 addenda — no hand-shaped records,
    # no hand-shaped cross files).
    import tempfile
    from derive_gate3_arming import gate3_inputs as gi  # noqa: F401
    from driver_video import cross_gates, record_from_li

    def rec(labels, scores, chars, video):
        body = {'chunks': ['x' * c for c in chars], 'chunk_chars': chars,
                'n_chunks': len(chars), 'n_frames': len(labels),
                'n_detections': sum(len(f) for f in labels),
                'detections_per_frame': [len(f) for f in labels],
                'frame_labels': labels, 'frame_scores': scores,
                'embed_dim': 3, 'embedding_norms': [1.0],
                'stage_s': {'extract': 1.0, 'detect': 6.0, 'split': 0.5,
                            'embed': 2.5}, 'pid': 1}
        r = record_from_li(body)
        r['video'] = video
        return r

    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        # film A diverges in the BACK half (drift shape), rr detects more;
        # film B agrees exactly.
        rr_rows = [rec([['a'], ['a'], ['a', 'b'], ['a', 'b']],
                       [[0.9], [0.9], [0.9, 0.8], [0.9, 0.8]],
                       [100, 100], 'A.mp4'),
                   rec([['c']], [[0.7]], [50], 'B.mp4')]
        li_rows = [rec([['a'], ['a'], ['a'], ['a']],
                       [[0.9], [0.9], [0.9], [0.9]],
                       [90, 90], 'A.mp4'),
                   rec([['c']], [[0.7]], [50], 'B.mp4')]
        rrp, lip = d / 'rr.jsonl', d / 'li.jsonl'
        rrp.write_text('\n'.join(json.dumps(r) for r in rr_rows) + '\n')
        lip.write_text('\n'.join(json.dumps(r) for r in li_rows) + '\n')
        cross = cross_gates(rrp, lip, 0.02, gate3_armed='selftest')
        rr_by, li_by = load_records(rrp), load_records(lip)

        a = frame_anatomy(rr_by['A.mp4'], li_by['A.mp4'])
        check('anatomy: 2/4 diverging, both count-mismatch, rr detects more',
              a['n_diverging'] == 2
              and a['split']['count_mismatch'] == 2
              and a['direction']['rr_more_detections'] == 2)
        check('index pattern: clean prefix 2, back-half rate 1.0/1.0 '
              '(the drift signature the tool exists to see)',
              a['index_pattern']['longest_clean_prefix'] == 2
              and a['index_pattern']['diverging_rate_by_quartile'] == [0.0, 0.0, 1.0, 1.0])
        check('side-by-side dump carries both arms at frame 2',
              a['first_diverging_frames'][0]['frame'] == 2
              and a['first_diverging_frames'][0]['rr']['labels'] == ['a', 'b'])
        null = frame_anatomy(rr_by['B.mp4'], li_by['B.mp4'])
        check('null control: identical film -> 0 diverging',
              null['n_diverging'] == 0
              and null['index_pattern']['longest_clean_prefix'] == 1)
        band = char_band_data(cross)
        check('char band data from the PRODUCER-built cross file '
              '(A 200/180, B 50/50)',
              band['n'] == 2 and band['max'] == round(200 / 180, 4)
              and band['min'] == 1.0)
        cj = confound_join(cross, rr_by, li_by)
        check('confound join: diverging film carries the off-1 ratio',
              cj['confound_probe']['median_char_ratio_high_divergence_half']
              == round(abs(200 / 180 - 1), 4)
              and cj['per_film'][0]['n_diverging'] == 2)
        share = li_embed_share(li_by)
        check('LI embed share computed from stage_s (2.5/10 = 0.25)',
              share['stage_share']['embed'] == 0.25)
        dirn = corpus_direction(rr_by, li_by)
        check('corpus direction: rr-more on 1 film, tie on 1',
              dirn['films_where_rr_detects_more'] == 1
              and dirn['films_where_li_detects_more'] == 0)

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
    ap.add_argument('--results-dir', default=None,
                    help='campaign dir; default = newest '
                         'working/video/results/films_mainrun_*')
    ap.add_argument('--film', default='HouseOnBareMountain.mp4',
                    help='film for the per-frame anatomy (an operator-named '
                         'failing film; also the golden film)')
    ap.add_argument('--cell', default='parity_blast',
                    help='cell for records + cross join (pass-1 files)')
    ap.add_argument('--dump-n', type=int, default=6)
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    if args.self_test:
        return self_test()

    root = Path(__file__).resolve().parents[1] / 'results'
    out_dir = Path(args.results_dir).expanduser() if args.results_dir \
        else newest_results_dir(root)
    print(f'diagnosing: {out_dir}')
    posture, leg = args.cell.split('_', 1)
    rr_by = load_records(out_dir / f'records_rocketride_video_{posture}_{leg}.jsonl')
    li_by = load_records(out_dir / f'records_llamaindex_video_workers_{leg}.jsonl')
    cross_path = out_dir / f'cross_{args.cell}.json'
    cross = json.loads(cross_path.read_text())

    print(f'\n== TASK 2: per-frame anatomy — {args.film} [{args.cell}] ==')
    if args.film not in rr_by or args.film not in li_by:
        raise SystemExit(f'NOT DONE — {args.film} not in both record sets '
                         f'(rr {len(rr_by)}, li {len(li_by)} films)')
    print(json.dumps(frame_anatomy(rr_by[args.film], li_by[args.film],
                                   args.dump_n), indent=1))
    print('\n== corpus-wide detection direction ==')
    dirn = corpus_direction(rr_by, li_by)
    print(json.dumps({k: v for k, v in dirn.items() if k != 'per_film'},
                     indent=1))
    print(json.dumps(dirn['per_film'][:10], indent=1))

    print('\n== TASK 4: char_conservation band data (Ruling T: DATA, not a '
          'headline) ==')
    for cf in sorted(out_dir.glob('cross_*.json')):
        c = json.loads(cf.read_text())
        print(f'  {cf.name}: {json.dumps(char_band_data(c))}')
    print('\n== confound join (char ratio vs divergence vs det ratio) ==')
    cj = confound_join(cross, rr_by, li_by)
    print(json.dumps(cj['confound_probe'], indent=1))
    print(json.dumps(cj['per_film'][:12], indent=1))
    print('\n== LI embed share (bounds the throughput confound) ==')
    print(json.dumps(li_embed_share(li_by), indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
