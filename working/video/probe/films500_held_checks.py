#!/usr/bin/env python3
"""films500_held_checks — reproduces, from the LANDED files, every derived
figure the Films-500 FINAL report cites that is not itself a field of an
export or a record (added 2026-09-07 so that no figure rests on a session
computation). Each block prints its figures beside the files it read.

  A. within-arm and cross-lifetime bit-identity (labels, full-precision
     scores, chunk shas) — campaign p1 vs p2, lifetimes p3 vs p4, campaign p2
     vs lifetimes p3; and the cross-arm partition reproduced on the lifetimes
     run (report §5, §7 row 1)
  B. RR/LI per-film s-per-frame ratio by 560px class and by source
     resolution; LI per-stage seconds per frame by class and resolution
     (report §6 "the work is symmetric", §7 row 4)
  C. warm-up send medians per pass, both arms; CPU-s/frame per RR pass
     (report §4, the excluded pass-1 pair)
  D. corpus facade-reduction figures: per-film area ratio range and
     frames-weighted mean, pixels handed to predict per arm, model pixels
     (report §6)
  E. manifest-row identity: every record's frames / duration / bytes /
     submitted sha vs the committed manifest row, all blast legs (report §9)
  F. per-leg export figures used in §2: effective cores, per-core rates,
     idle burden, spreads (read straight from the exports; printed for the
     reader beside the derived means)

Run:  python3 working/video/probe/films500_held_checks.py
"""

from __future__ import annotations

import collections
import json
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
V = HERE.parents[1]
MANIFEST = V / 'films500_video_manifest.jsonl'
CAMP = V / 'results' / 'films500_mainrun_20260904T204852Z'
LIFE = V / 'results' / 'films500_lifetimes_20260906T090339Z'
RR, LI = 'rocketride_video_parity', 'llamaindex_video_workers'


def manifest():
    rows = [json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip()]
    films = {r['file']: r for r in rows if 'file' in r}
    return rows, films


def records(run: Path, arm: str, p: int) -> dict:
    f = run / f'records_{arm}_blast{"" if p == 1 else f"_p{p}"}.jsonl'
    last = {}
    for l in f.read_text().splitlines():
        if l.strip():
            r = json.loads(l)
            last[r.get('video')] = r
    return {k: v for k, v in last.items() if 'error' not in v}


def export(run: Path, arm: str, p: int) -> dict:
    return json.loads((run / f'export_{arm}_blast{"" if p == 1 else f"_p{p}"}.json').read_text())


def same(a: dict, b: dict) -> bool:
    return (a.get('frame_label_multisets') == b.get('frame_label_multisets')
            and a.get('frame_scores') == b.get('frame_scores')
            and a.get('chunk_sha256') == b.get('chunk_sha256'))


def block_a(films):
    print('=== A. bit-identity within arm, across passes and lifetimes (labels+scores+chunks) ===')
    edge = {f: max(r['detector_width'], r['detector_height']) > 560 for f, r in films.items()}
    legs = {(arm, 1): records(CAMP, arm, 1), (arm, 2): records(CAMP, arm, 2),
            (arm, 3): records(LIFE, arm, 3), (arm, 4): records(LIFE, arm, 4)}
    for arm, tag in ((RR, 'RR'), (LI, 'LI')):
        legs.update({(arm, p): records(CAMP if p <= 2 else LIFE, arm, p) for p in (1, 2, 3, 4)})
        for (pa, pb, what) in ((1, 2, 'campaign p1 vs p2, one lifetime'), (3, 4, 'lifetimes p3 vs p4, one lifetime'),
                               (2, 3, 'campaign p2 vs lifetimes p3, DIFFERENT lifetimes, 2 days apart')):
            a, b = legs[(arm, pa)], legs[(arm, pb)]
            n = sum(same(a[v], b[v]) for v in a if v in b)
            print(f'  {tag} {what}: identical {n}/{len(a)}  (>560 films among them: {sum(1 for v in a if v in b and edge[v])})')
    rr3, li3 = legs[(RR, 3)], legs[(LI, 3)]
    diff = [v for v in rr3 if v in li3 and not (rr3[v].get('frame_label_multisets') == li3[v].get('frame_label_multisets')
                                             and rr3[v].get('frame_scores') == li3[v].get('frame_scores'))]
    print(f'  cross-arm on lifetimes p3 (no partition step ran): differing above-560 {sum(edge[v] for v in diff)}, '
          f'below-560 {sum(not edge[v] for v in diff)}  [records_*_blast_p3.jsonl]')


def block_b(films):
    print('=== B. RR/LI cost ratio by 560px class and by resolution; LI per-stage flatness (campaign p2) ===')
    edge = {f: max(r['detector_width'], r['detector_height']) > 560 for f, r in films.items()}
    fr = {f: r['expected_frames_measured'] for f, r in films.items()}
    for p in (1, 2):
        rr, li = records(CAMP, RR, p), records(CAMP, LI, p)
        ratios = {'<=560': [], '>560': []}
        for v in rr:
            if v in li and v in films:
                ratios['>560' if edge[v] else '<=560'].append((rr[v]['wall_s'] / fr[v]) / (li[v]['wall_s'] / fr[v]))
        print(f'  pass {p}: RR/LI s-per-frame ratio median <=560 {st.median(ratios["<=560"]):.3f} (n={len(ratios["<=560"])}) | '
              f'>560 {st.median(ratios[">560"]):.3f} (n={len(ratios[">560"])})')
    rr, li = records(CAMP, RR, 2), records(CAMP, LI, 2)
    byres = collections.defaultdict(lambda: {'rr': [], 'li': []})
    for v in rr:
        if v in li and v in films:
            k = (films[v]['detector_width'], films[v]['detector_height'])
            byres[k]['rr'].append(rr[v]['wall_s'] / fr[v]); byres[k]['li'].append(li[v]['wall_s'] / fr[v])
    for k, d in sorted(byres.items(), key=lambda kv: -len(kv[1]['rr'])):
        if len(d['rr']) >= 5:
            print(f'  pass 2 {k[0]}x{k[1]} (n={len(d["rr"])}): RR {st.median(d["rr"]):.2f} s/frame, LI {st.median(d["li"]):.2f}, '
                  f'ratio {st.median(d["rr"]) / st.median(d["li"]):.3f}')
    stage = collections.defaultdict(lambda: collections.defaultdict(list))
    for v, r in li.items():
        if v in films and isinstance(r.get('stage_s'), dict):
            k = (films[v]['detector_width'], films[v]['detector_height'])
            for s, val in r['stage_s'].items():
                stage[s][k].append(val / fr[v])
                stage[s]['>560' if edge[v] else '<=560'].append(val / fr[v])
    for s in ('extract', 'detect'):
        line = ' | '.join(f'{k if isinstance(k, str) else f"{k[0]}x{k[1]}"} {st.median(x):.3f}'
                          for k, x in stage[s].items() if len(x) >= 5)
        print(f'  LI stage {s} s/frame: {line}')


def block_c(films):
    print('=== C. warm-up send medians per pass; RR CPU-s/frame per pass (the excluded p1 pair) ===')
    for arm, tag in ((RR, 'RR'), (LI, 'LI')):
        for p in (1, 2, 3, 4):
            run = CAMP if p <= 2 else LIFE
            w = json.loads((run / f'warmup_{arm}_blast{"" if p == 1 else f"_p{p}"}.json').read_text())['sends']
            ws = [s['wall_s'] for s in w if s.get('wall_s')]
            print(f'  {tag} p{p}: {len(ws)} warm-up sends, median {st.median(ws):.0f} s (min {min(ws):.0f}, max {max(ws):.0f})')
    for p in (1, 2, 3, 4):
        e = export(CAMP if p <= 2 else LIFE, RR, p)
        print(f'  RR p{p}: span {e["throughput"]["total_frames_per_s"]} f/s, CPU-s/frame {e["efficiency"]["cpu_s_per_frame"]}, '
              f'util {e["efficiency"]["cpu_util_of_box"] * 100:.1f}%, preleg load1 {e.get("preleg_load1")}')


def block_d(films):
    print('=== D. corpus facade-reduction figures (detector-basis dimensions, measured films) ===')
    def facade(w, h):
        if max(w, h) <= 560:
            return w, h
        s = 560 / max(w, h)
        return max(1, int(w * s)), max(1, int(h * s))
    meas = [r for r in films.values() if r['role'] == 'measured']
    above = [r for r in meas if max(r['detector_width'], r['detector_height']) > 560]
    ratios = [facade(r['detector_width'], r['detector_height'])[0] * facade(r['detector_width'], r['detector_height'])[1]
              / (r['detector_width'] * r['detector_height']) for r in above]
    wmean = sum(x * r['expected_frames_measured'] for x, r in zip(ratios, above)) / sum(r['expected_frames_measured'] for r in above)
    src = sum(r['detector_width'] * r['detector_height'] * r['expected_frames_measured'] for r in meas)
    fac = sum(facade(r['detector_width'], r['detector_height'])[0] * facade(r['detector_width'], r['detector_height'])[1]
              * r['expected_frames_measured'] for r in meas)
    frames = sum(r['expected_frames_measured'] for r in meas)
    print(f'  measured films {len(meas)}, above 560: {len(above)}; area ratio min {min(ratios):.3f} max {max(ratios):.3f} '
          f'frames-weighted mean {wmean:.3f}; pixels to predict LI {src / 1e9:.2f} Gpx vs RR {fac / 1e9:.2f} Gpx; '
          f'model pixels 560x560 x {frames} frames = {313600 * frames / 1e9:.2f} Gpx both arms')
    exact = [f for f, r in films.items() if max(r['detector_width'], r['detector_height']) == 560]
    print(f'  films with long edge exactly 560: {exact}')


def block_e(films):
    print('=== E. manifest-row identity: records vs the committed manifest, all blast legs ===')
    bad_total = 0
    for run, ps in ((CAMP, (1, 2)), (LIFE, (3, 4))):
        for arm in (RR, LI):
            for p in ps:
                rec = records(run, arm, p)
                bad = [v for v, r in rec.items() if v in films and (
                    r.get('expected_frames') != films[v]['expected_frames_measured']
                    or abs((r.get('video_s_manifest') or 0) - films[v]['video_s']) > 1e-6
                    or r.get('bytes') != films[v]['bytes'] or r.get('submitted_sha256') != films[v]['sha256'])]
                bad_total += len(bad)
                print(f'  {run.name[9:18]} {arm[:10]} p{p}: {len(rec) - len(bad)}/{len(rec)} rows identical to the committed manifest')
    print(f'  TOTAL mismatching films: {bad_total}')


def block_f():
    print('=== F. per-leg export figures behind §2 (fields read from the landed exports) ===')
    rows = {}
    for arm, tag in ((RR, 'RR'), (LI, 'LI')):
        for p in (1, 2, 3, 4):
            e = export(CAMP if p <= 2 else LIFE, arm, p)
            f, c = e['throughput']['total_frames_per_s'], e['efficiency']['effective_cores']
            idle = e['efficiency']['idle_burden']['idle_cores_with_instances_live']
            rows[(tag, p)] = (f, c, idle)
            print(f'  {tag} p{p}: span {f} f/s | cores {c} | idle {idle} | per measured core {f / c:.4f} | per effective core {f / (c - idle):.4f} '
                  f'| CPU-s/frame {e["efficiency"]["cpu_s_per_frame"]} | $/1k {e["efficiency"]["usd_per_1k_footage_hours"]}')
    def mean(tag, ps, i):
        return st.mean(rows[(tag, p)][i] for p in ps)
    for label, ps in (('lifetimes p3+p4', (3, 4)), ('settled p2+p3+p4', (2, 3, 4))):
        lf, lc, li_ = mean('LI', ps, 0), mean('LI', ps, 1), mean('LI', ps, 2)
        rf, rc, ri = mean('RR', ps, 0), mean('RR', ps, 1), mean('RR', ps, 2)
        print(f'  {label}: span LI {lf:.3f} vs RR {rf:.3f} = {lf / rf - 1:+.1%} | per measured core {(lf / lc) / (rf / rc) - 1:+.1%} | '
              f'per effective core {(lf / (lc - li_)) / (rf / (rc - ri)) - 1:+.1%}')
    print(f'  spreads: RR p3/p4 {abs(rows[("RR", 3)][0] / rows[("RR", 4)][0] - 1):.2%}, LI p3/p4 {abs(rows[("LI", 3)][0] / rows[("LI", 4)][0] - 1):.2%}')


def main() -> int:
    rows, films = manifest()
    print(f'manifest: {MANIFEST.name}, {len(films)} films; campaign {CAMP.name}; lifetimes {LIFE.name}')
    block_a(films); block_b(films); block_c(films); block_d(films); block_e(films); block_f()
    return 0


if __name__ == '__main__':
    sys.exit(main())
