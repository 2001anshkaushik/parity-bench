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
        print(f'  [{key}]')
        for i, m in enumerate(members):
            keep = ' KEEP (largest bytes)' if i == 0 else ' drop'
            print(f'    {m["doc"]}: {m["bytes"]} B, {m["duration_s"]:.0f}s{keep}')

    strata, (dlo, dhi), (blo, bhi) = stratify(kept)
    print(f'\nstrata over deduped titles: duration terciles at '
          f'({dlo:.0f}s, {dhi:.0f}s), bytes terciles at ({blo}, {bhi})')
    for cell in sorted(strata):
        members = strata[cell]
        first = ', '.join(m['doc'] for m in members[:min(3, k + 1)])
        print(f'  D{cell[0]}xB{cell[1]}: {len(members)} titles; '
              f'selection order head: {first}')
    n_total = sum(min(k, len(v)) for v in strata.values())
    print(f'\nwith k={k} per stratum the subset would be N={n_total} '
          f'(+1 if the envelope film is not already selected) — N stays '
          'OPEN; the sizing probe prices it and Ansh rules.')

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
