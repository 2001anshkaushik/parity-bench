#!/usr/bin/env python3
"""films_strata_report — the mechanical TASK-3(a) analysis over Leela's
frozen corpus_manifest.json (design support: reports, sets nothing; N stays
open for the sizing probe's projection and Ansh's ruling).

Reports, all derived deterministically from the manifest:
  * duration_s and bytes distributions (min / p25 / median / p75 / max);
  * duplicate-title clusters, detected MECHANICALLY: doc name -> title key
    by casefold, strip extension, remove every non-alphanumeric, strip
    4-digit year tokens (18xx/19xx/20xx) — so his_girl_friday and
    HisGirlFriday-1940 collapse to one key, as do the Carnival of Souls /
    Bucket of Blood / Gulliver's Travels transcode families. EXACT key
    equality only — no fuzzy matching, nothing eyeballed;
  * the ONE-TRANSCODE-PER-TITLE dedup (Ansh's ruling): keep the
    LARGEST-bytes member per title (decode-work-maximal), ties broken by
    doc name ascending — deterministic from the manifest;
  * duration-tercile x bytes-tercile strata over the deduped titles
    (cutoffs printed), per-stratum counts and the first three members by
    (bytes desc, doc asc) — the selection order a later cut takes k from;
  * the PROBE FILM under the stated rule: the globally largest-bytes title
    after dedup (the sizing envelope: worst decode + worst spool + worst
    upload in one film; a serial projection from it is an upper bound).

Everything printed is a pure function of the manifest bytes; the manifest's
own sha256 is printed first so the report is bound to its input.

Run (box):  python3 working/video/probe/films_strata_report.py \
                [--manifest ~/films_manifest/corpus_manifest.json] [--k 2]
Self-test:  --self-test (synthetic manifest; no files needed)
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # working/video
from argtypes import positive_int          # noqa: E402 — register entry 8

_YEAR = re.compile(r'(18|19|20)\d\d')
_NONALNUM = re.compile(r'[^a-z0-9]+')

# RULING E (2026-08-28), recorded IN the rule so the output stays
# deterministic and reproducible — never a hand edit: these prefix merges
# were RATIFIED AS SPLITS (different films): killer_dill (1948 Stuart Erwin
# comedy) vs killer_diller (1948 all-Black-cast musical); DanielBoone1936 vs
# Daniel_Boone_-_Trail_Blazer (1956). The 10% duration window is KEPT (it
# produced 17 correct clusters; the ratification step caught the two
# over-merges, working as designed).
RATIFIED_SPLITS = frozenset({
    frozenset({'killerdill', 'killerdiller'}),
    frozenset({'danielboone', 'danielboonetrailblazer'}),
})
# Flagged by Ansh, NOT acted on (cost is one film if wrong): [waterfront]
# (waterfront_lady_1935 4100s vs waterfront 3829s) may be a third false
# merge. It stays merged until ruled; the report prints the flag.
UNRATIFIED_FLAGS = frozenset({'waterfront'})


def title_key(doc: str) -> str:
    """Mechanical normalization: casefold, drop extension, drop 4-digit
    years, drop every non-alphanumeric. Exact-equality grouping only."""
    stem = doc.rsplit('.', 1)[0].casefold()
    stem = _YEAR.sub('', stem)
    return _NONALNUM.sub('', stem)


def quantiles(vals):
    v = sorted(vals)
    n = len(v)
    pick = lambda q: v[min(n - 1, int(q * n))]   # noqa: E731 — index quantile, deterministic
    return {'min': v[0], 'p25': pick(0.25), 'median': pick(0.50),
            'p75': pick(0.75), 'max': v[-1], 'n': n}


def load_rows(manifest: dict):
    """One row per doc: (doc, duration_s, video_duration_s, bytes, sha)."""
    shas = manifest['sha256']
    rows = []
    for doc in sorted(shas):
        rows.append({'doc': doc,
                     'duration_s': manifest['duration_s'][doc],
                     'video_duration_s': manifest['video_duration_s'][doc],
                     'bytes': shas[doc]['bytes'],
                     'sha256': shas[doc]['sha256']})
    return rows


def dedup_titles(rows, dup_duration_pct: float = 10.0):
    """Ansh's rule: one transcode per title — keep largest bytes, tie by
    doc asc. Two mechanical detectors, both deterministic:
      v1  exact normalized-key equality;
      v2  PREFIX merge: key A (len >= 8) is a prefix of key B AND the two
          groups' closest durations are within dup_duration_pct — catches
          junk-suffixed transcodes (…VideoQualityUpgrade, …720p_652,
          …1939_201509) that v1 provably missed on this corpus
          (CarnivalOfSouls x3 and GulliversTravels x3 were the measured
          counterexamples, 2026-08-28). v2 was added against named
          counterexamples, so the FULL cluster list is printed for human
          ratification — a merged false positive would be visible there,
          and the 10% window is a chosen value flagged for Ansh's ruling.
    Returns (kept_rows, clusters); clusters fully listed."""
    by_key = {}
    for r in rows:
        by_key.setdefault(title_key(r['doc']), []).append(r)

    keys = sorted(by_key)
    parent = {k: k for k in keys}

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    def close_enough(g1, g2):
        return any(abs(a['duration_s'] - b['duration_s'])
                   <= dup_duration_pct / 100.0 * min(a['duration_s'],
                                                     b['duration_s'])
                   for a in g1 for b in g2)

    for i, k1 in enumerate(keys):
        if len(k1) < 8:
            continue
        for k2 in keys[i + 1:]:
            if not k2.startswith(k1):
                break          # keys sorted: prefixes are adjacent
            if frozenset({k1, k2}) in RATIFIED_SPLITS:
                continue       # RULING E: ratified different-film pair
            if close_enough(by_key[k1], by_key[k2]):
                parent[find(k2)] = find(k1)

    groups = {}
    for k in keys:
        groups.setdefault(find(k), []).extend(by_key[k])
    clusters = {k: sorted(v, key=lambda r: (-r['bytes'], r['doc']))
                for k, v in groups.items() if len(v) > 1}
    kept = [sorted(v, key=lambda r: (-r['bytes'], r['doc']))[0]
            for v in groups.values()]
    return sorted(kept, key=lambda r: r['doc']), clusters


def tercile_cuts(vals):
    v = sorted(vals)
    n = len(v)
    return v[n // 3], v[(2 * n) // 3]


def stratify(kept):
    dur_lo, dur_hi = tercile_cuts([r['duration_s'] for r in kept])
    byt_lo, byt_hi = tercile_cuts([r['bytes'] for r in kept])
    tier = lambda x, lo, hi: 0 if x < lo else (1 if x < hi else 2)  # noqa: E731
    strata = {}
    for r in kept:
        cell = (tier(r['duration_s'], dur_lo, dur_hi),
                tier(r['bytes'], byt_lo, byt_hi))
        strata.setdefault(cell, []).append(r)
    for cell in strata:
        strata[cell].sort(key=lambda r: (-r['bytes'], r['doc']))
    return strata, (dur_lo, dur_hi), (byt_lo, byt_hi)


def probe_film(kept):
    """The stated rule: globally largest bytes after dedup (tie: doc asc)."""
    return sorted(kept, key=lambda r: (-r['bytes'], r['doc']))[0]


# RULING J (2026-08-28): the warm pair — two dedicated warm films, disjoint
# from the measured selection, by deterministic rule: the NEXT candidate in
# (bytes desc, doc asc) order from D0xB0 (short regime) and D2xB2 (long
# regime), role='warm', WARM_N=2. Warm coverage spans the decode range the
# leg will see. Reasoning recorded with the ruling: (c) warming with
# measured films breaks warmed-never-measured, a correctness property not a
# tuning knob; (d) AMI items exercise neither the 1080p decode path nor
# films-sized spools, so the first measured film would still pay the cold
# cost warm-up exists to absorb; (a) positional inheritance is inapplicable
# (our subset is our rule over her corpus — no her-order to be positional
# in). Crossroad 32/40/41 mechanics carry unchanged.
WARM_CELLS = ((0, 0), (2, 2))


def select_warm_pair(kept, selected_docs):
    """The RULING J warm films: first unselected candidate per WARM_CELLS,
    in the same (bytes desc, doc asc) selection order. One copy — the
    report prints it and the manifest builder consumes it."""
    strata, _, _ = stratify(kept)
    warm = []
    for cell in WARM_CELLS:
        pick = next((r for r in strata.get(cell, [])
                     if r['doc'] not in selected_docs
                     and r['doc'] not in {w['doc'] for w in warm}), None)
        if pick is None:
            raise SystemExit(f'NOT DONE — no unselected warm candidate in '
                             f'stratum D{cell[0]}xB{cell[1]} (Ruling J needs '
                             'one; the cell is exhausted)')
        warm.append(pick)
    return warm


def select_subset(kept, k: int):
    """RULING F selection, one copy (report prints it, the manifest builder
    consumes it): k per stratum in (bytes desc, doc asc) order, capped by
    cell size; the envelope film forced in if not already selected.
    Returns (selected_rows_sorted_by_doc, strata_meta)."""
    strata, (dlo, dhi), (blo, bhi) = stratify(kept)
    chosen, by_cell = {}, {}
    for cell in sorted(strata):
        take = strata[cell][:k]
        by_cell[f'D{cell[0]}xB{cell[1]}'] = [r['doc'] for r in take]
        for r in take:
            chosen[r['doc']] = r
    env = probe_film(kept)
    envelope_forced = env['doc'] not in chosen
    if envelope_forced:
        chosen[env['doc']] = env
        by_cell.setdefault('envelope_forced', []).append(env['doc'])
    meta = {'k': k, 'duration_tercile_cuts_s': [dlo, dhi],
            'bytes_tercile_cuts': [blo, bhi], 'per_cell': by_cell,
            'envelope_film': env['doc'], 'envelope_forced': envelope_forced,
            'n_selected': len(chosen)}
    return sorted(chosen.values(), key=lambda r: r['doc']), meta


def report(manifest_path: Path, k: int) -> int:
    data = manifest_path.read_bytes()
    print(f'manifest: {manifest_path}')
    print(f'manifest sha256: {hashlib.sha256(data).hexdigest()}')
    manifest = json.loads(data)
    rows = load_rows(manifest)
    print(f'docs: {len(rows)}')
    dq = quantiles([r["duration_s"] for r in rows])
    bq = quantiles([r["bytes"] for r in rows])
    print(f'duration_s: {json.dumps(dq)}')
    print(f'bytes     : {json.dumps(bq)}')

    kept, clusters = dedup_titles(rows)
    print(f'\nduplicate-title clusters (mechanical key; exact equality): '
          f'{len(clusters)} clusters, '
          f'{sum(len(v) for v in clusters.values())} member files, '
          f'{len(rows)} docs -> {len(kept)} distinct titles')
    for key, members in sorted(clusters.items()):
        flag = ('  <-- UNRATIFIED FLAG (Ruling E): possible false merge, '
                'left merged until ruled; cost one film'
                if key in UNRATIFIED_FLAGS else '')
        print(f'  [{key}]{flag}')
        for i, m in enumerate(members):
            keep = ' KEEP (largest bytes)' if i == 0 else ' drop'
            print(f'    {m["doc"]}: {m["bytes"]} B, {m["duration_s"]:.0f}s{keep}')
    print(f'  ratified splits applied (Ruling E, in-rule, deterministic): '
          f'{sorted(tuple(sorted(s)) for s in RATIFIED_SPLITS)}')

    strata, (dlo, dhi), (blo, bhi) = stratify(kept)
    print(f'\nstrata over deduped titles: duration terciles at '
          f'({dlo:.0f}s, {dhi:.0f}s), bytes terciles at ({blo}, {bhi})')
    for cell in sorted(strata):
        members = strata[cell]
        first = ', '.join(m['doc'] for m in members[:min(3, k + 1)])
        print(f'  D{cell[0]}xB{cell[1]}: {len(members)} titles; '
              f'selection order head: {first}')
    selected, smeta = select_subset(kept, k)
    print(f'\nSELECTION at k={k} (Ruling F rule: k per stratum by (bytes '
          f'desc, doc asc), capped by cell size, envelope forced if absent): '
          f'N={smeta["n_selected"]}, envelope_forced={smeta["envelope_forced"]}')
    for cell, docs in sorted(smeta['per_cell'].items()):
        print(f'  {cell}: {", ".join(docs)}')

    warm = select_warm_pair(kept, {r['doc'] for r in selected})
    print(f'\nWARM PAIR (Ruling J: next unselected candidate from D0xB0 and '
          f'D2xB2, disjoint from the {smeta["n_selected"]} measured): '
          + ', '.join(f'{w["doc"]} ({w["bytes"]} B, {w["duration_s"]:.0f}s)'
                      for w in warm))

    pf = probe_film(kept)
    print(f'\nPROBE FILM (rule: globally largest bytes after dedup): '
          f'{pf["doc"]} — {pf["bytes"]} B, duration {pf["duration_s"]:.0f}s, '
          f'video_duration {pf["video_duration_s"]:.0f}s, sha {pf["sha256"]}')
    return 0


def self_test() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f'  {"PASS" if cond else "FAIL"}  {name}')
        ok = ok and cond

    check('title_key collapses underscore/camel/year variants',
          title_key('his_girl_friday.mp4') == title_key('HisGirlFriday-1940.mp4'))
    check('title_key collapses transcode-suffix variants',
          title_key('CarnivalOfSouls.mp4') == title_key('carnival_of_souls_1962.mp4'))
    check('title_key keeps distinct titles distinct',
          title_key('ABucketofBlood.mp4') != title_key('AStarIsBorn.mp4'))

    docs = {
        'his_girl_friday.mp4': (5000, 900_000),
        'HisGirlFriday-1940.mp4': (5010, 1_200_000),   # same title, bigger
        'unique_a.mp4': (4000, 500_000),
        'unique_b.mp4': (6000, 700_000),
        'unique_c.mp4': (7000, 2_000_000),
        'unique_d.mp4': (3000, 300_000),
    }
    manifest = {'duration_s': {d: v[0] for d, v in docs.items()},
                'video_duration_s': {d: v[0] - 1 for d, v in docs.items()},
                'sha256': {d: {'sha256': 'ab' * 32, 'bytes': v[1]}
                           for d, v in docs.items()}}
    rows = load_rows(manifest)
    kept, clusters = dedup_titles(rows)
    check('cluster detected mechanically (1 cluster, 2 members)',
          len(clusters) == 1 and len(next(iter(clusters.values()))) == 2)
    check('dedup keeps the LARGEST-bytes transcode',
          any(r['doc'] == 'HisGirlFriday-1940.mp4' for r in kept)
          and not any(r['doc'] == 'his_girl_friday.mp4' for r in kept))
    check('5 distinct titles remain from 6 docs', len(kept) == 5)

    # v2 prefix merge: the measured counterexamples' shape (junk suffixes).
    tri = {'gullivers_travels1939.mp4': (4360, 454_000_000),
           'GulliversTravels720p_652.mp4': (4583, 475_808_316),
           'GulliversTravels1939_201509.mp4': (4586, 476_779_476),
           'unrelated.mp4': (4500, 400_000_000)}
    m2 = {'duration_s': {d: v[0] for d, v in tri.items()},
          'video_duration_s': {d: v[0] for d, v in tri.items()},
          'sha256': {d: {'sha256': 'cd' * 32, 'bytes': v[1]}
                     for d, v in tri.items()}}
    kept2, cl2 = dedup_titles(load_rows(m2))
    check('v2 prefix merge clusters the junk-suffixed trio into ONE title',
          len(cl2) == 1 and len(next(iter(cl2.values()))) == 3
          and len(kept2) == 2)
    check('v2 keeps the largest-bytes member of the merged trio',
          any(r['doc'] == 'GulliversTravels1939_201509.mp4' for r in kept2))

    # v2 guard: a prefix pair FAR apart in duration is NOT merged.
    far = {'thegolem.mp4': (3600, 1), 'TheGolemHowHeCame.mp4': (6200, 2)}
    m3 = {'duration_s': {d: v[0] for d, v in far.items()},
          'video_duration_s': {d: v[0] for d, v in far.items()},
          'sha256': {d: {'sha256': 'ef' * 32, 'bytes': v[1]}
                     for d, v in far.items()}}
    _, cl3 = dedup_titles(load_rows(m3))
    check('v2 guard: prefix match beyond the duration window stays unmerged',
          len(cl3) == 0)

    # RULING E: the ratified splits stay split even inside the window.
    rul = {'killer_dill.mp4': (4322, 450_591_179),
           'killer_diller.mp4': (4373, 893_689_958)}
    m4 = {'duration_s': {d: v[0] for d, v in rul.items()},
          'video_duration_s': {d: v[0] for d, v in rul.items()},
          'sha256': {d: {'sha256': 'aa' * 32, 'bytes': v[1]}
                     for d, v in rul.items()}}
    kept4, cl4 = dedup_titles(load_rows(m4))
    check('Ruling E: ratified split pair never merges (both titles kept)',
          len(cl4) == 0 and len(kept4) == 2)

    # RULING F selection: deterministic, capped, envelope forced.
    many = {f'f{i:02d}.mp4': (3000 + i * 400, 100_000 + i * 10_000)
            for i in range(9)}
    m5 = {'duration_s': {d: v[0] for d, v in many.items()},
          'video_duration_s': {d: v[0] for d, v in many.items()},
          'sha256': {d: {'sha256': 'bb' * 32, 'bytes': v[1]}
                     for d, v in many.items()}}
    kept5, _ = dedup_titles(load_rows(m5))
    sel_a, meta_a = select_subset(kept5, 2)
    sel_b, meta_b = select_subset(kept5, 2)
    check('Ruling F selection is deterministic (two runs identical)',
          [r['doc'] for r in sel_a] == [r['doc'] for r in sel_b]
          and meta_a == meta_b)
    check('Ruling F: k caps at cell size and N = sum of takes',
          meta_a['n_selected'] == len(sel_a) <= 2 * 9)
    check('Ruling F: envelope film is in the selection',
          any(r['doc'] == meta_a['envelope_film'] for r in sel_a))

    # RULING J: warm pair — disjoint, deterministic, from the two corner cells.
    wp1 = select_warm_pair(kept5, {r['doc'] for r in sel_a})
    wp2 = select_warm_pair(kept5, {r['doc'] for r in sel_a})
    sel_docs = {r['doc'] for r in sel_a}
    check('Ruling J: warm pair is 2 films, disjoint from the selection',
          len(wp1) == 2 and not sel_docs & {w['doc'] for w in wp1})
    check('Ruling J: warm pair deterministic (two runs identical)',
          [w['doc'] for w in wp1] == [w['doc'] for w in wp2])
    strata5, _, _ = stratify(kept5)
    check('Ruling J: warm films come from D0xB0 and D2xB2',
          wp1[0]['doc'] in [r['doc'] for r in strata5[(0, 0)]]
          and wp1[1]['doc'] in [r['doc'] for r in strata5[(2, 2)]])
    strata, _, _ = stratify(kept)
    check('every kept title lands in exactly one stratum',
          sum(len(v) for v in strata.values()) == len(kept))
    pf = probe_film(kept)
    check('probe film = globally largest bytes after dedup',
          pf['doc'] == 'unique_c.mp4')
    q = quantiles([1, 2, 3, 4])
    check('quantiles deterministic (index rule)',
          q['min'] == 1 and q['max'] == 4 and q['median'] == 3)
    print('self-test:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 4


def main() -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--manifest',
                    default=str(Path.home() / 'films_manifest/corpus_manifest.json'))
    ap.add_argument('--k', type=positive_int('k', 50), default=2,
                    help='illustrative per-stratum count for the N preview '
                         '(N itself stays open — Ansh rules)')
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    p = Path(args.manifest).expanduser()
    if not p.is_file():
        raise SystemExit(f'NOT DONE — manifest not found: {p}')
    return report(p, args.k)


if __name__ == '__main__':
    sys.exit(main())
