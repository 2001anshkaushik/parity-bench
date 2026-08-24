#!/usr/bin/env bash
# Which number was "8/8"? probe_li_workers records TWO different censuses and
# the driver's warm-up gate uses only ONE of them. Run in the probe dir.
#   serving_by_cpu_delta   — processes that BURNED CPU during the batch (the
#                            probe's headline "serving"; its docstring calls
#                            this the proof)
#   distinct_response_pids — distinct pids that RETURNED a response. THIS is
#                            what the driver's warm-up coverage gate counts,
#                            and the probe's own docstring says it is expected
#                            to be < W on one batch.
# If the probe's 8/8 was serving_by_cpu_delta while distinct_response_pids was
# lower, the driver is gating on something the probe never demonstrated.
set -euo pipefail
PY="${PYBIN:-$HOME/.venv-floor/bin/python}"
cd "$(dirname "$0")"
"$PY" - "$@" <<'EOF'
import glob, json, sys
files = sys.argv[1:] or sorted(glob.glob('probe_li_workers*.json'))
if not files:
    print('NOT DONE — no probe_li_workers*.json here (pass paths as args)'); raise SystemExit(1)
for f in files:
    doc = json.load(open(f))
    points = doc if isinstance(doc, list) else doc.get('points') or [doc]
    print(f'== {f}')
    for p in points:
        if not isinstance(p, dict) or 'workers' not in p:
            continue
        w, ppw = p.get('workers'), p.get('posts_per_worker')
        cpu, resp = p.get('serving_by_cpu_delta'), p.get('distinct_response_pids')
        agree = '' if cpu == resp else '   <-- THE TWO CENSUSES DISAGREE'
        print(f'  W={w} ppw={ppw} posts={p.get("n_posts")}: '
              f'serving_by_cpu_delta={cpu}/{w}  distinct_response_pids={resp}/{w}{agree}')
        print(f'      response_pids={p.get("response_pids")}')
        print(f'      cpu_burner_pids={p.get("cpu_burner_pids")}  blind={p.get("census_blind_pids")}')
EOF
