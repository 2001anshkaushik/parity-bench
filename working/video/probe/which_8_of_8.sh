#!/usr/bin/env bash
# Which number was "8/8"? probe_li_workers records TWO different censuses and
# the driver's warm-up gate used only ONE of them (until Crossroad 41).
#   serving_by_cpu_delta   — processes that BURNED CPU during the batch; the
#                            probe's docstring calls this the serving proof
#   distinct_response_pids — distinct pids that RETURNED a response; the probe
#                            documents this as expected to be < W on one batch
# 2026-08-23: the first version of this tool printed headers and no rows. It
# filtered points on a key named 'workers'; the probe writes 'W'. A guessed
# field name is the same defect class as a guessed path — so it no longer
# guesses: it walks the document for any object carrying BOTH census fields,
# whatever it is called or however it is nested.
set -euo pipefail
PY="${PYBIN:-$HOME/.venv-floor/bin/python}"
cd "$(dirname "$0")"
"$PY" - "$@" <<'EOF'
import glob, json, sys

NEEDED = ('distinct_response_pids', 'serving_by_cpu_delta')

def points(node):
    if isinstance(node, dict):
        if all(k in node for k in NEEDED):
            yield node
        for v in node.values():
            yield from points(v)
    elif isinstance(node, list):
        for v in node:
            yield from points(v)

files = sys.argv[1:] or sorted(glob.glob('probe_li_workers*.json'))
if not files:
    print('NOT DONE — no probe_li_workers*.json here (pass paths as args)')
    raise SystemExit(1)
any_row = False
for f in files:
    try:
        doc = json.load(open(f))
    except Exception as e:                       # noqa: BLE001
        print(f'== {f}\n  UNREADABLE: {e!r}')
        continue
    rows = list(points(doc))
    print(f'== {f}  ({len(rows)} point(s) carrying both censuses)')
    if not rows:
        print(f'  no object in this file carries {NEEDED} — wrong file, or a probe '
              'output predating the two-census split. Top-level keys: '
              f'{sorted(doc)[:12] if isinstance(doc, dict) else type(doc).__name__}')
        continue
    for p in rows:
        any_row = True
        w = p.get('W', p.get('declared_workers', '?'))
        cpu, resp = p['serving_by_cpu_delta'], p['distinct_response_pids']
        flag = '' if cpu == resp else '   <-- THE TWO CENSUSES DISAGREE'
        print(f'  W={w} ppw={p.get("posts_per_worker")} posts={p.get("n_posts")}: '
              f'serving_by_cpu_delta={cpu}/{w}  distinct_response_pids={resp}/{w}{flag}')
        print(f'      response_pids   = {p.get("response_pids")}')
        print(f'      cpu_burner_pids = {p.get("cpu_burner_pids")}  blind={p.get("census_blind_pids")}')
raise SystemExit(0 if any_row else 1)
EOF
