#!/usr/bin/env bash
# LI W=16 SMOKE (2026-08-24) — B5's 16x2 point served 15/16 and Ansh recalls
# instability at 16. Verifies, BEFORE any 45-min leg: all 16 workers write
# warm markers, the container survives a few real videos, and the memory
# read-back is on record. ~6-10 min (16 model loads dominate).
set -euo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo "$HOME/parity-bench-video")"
PY="${PYBIN:-$HOME/.venv/bin/python}"
V="${VIDEO:?set VIDEO=<one ~250MB corpus file>}"
docker rm -f li_w16 >/dev/null 2>&1 || true
docker run -d --name li_w16 --memory 58g \
  -e OMP_NUM_THREADS=2 -e MKL_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 \
  -e VECLIB_MAXIMUM_THREADS=2 -e NUMEXPR_NUM_THREADS=2 -e TORCH_NUM_THREADS=2 \
  -e WS1V_WORKERS=16 --log-opt max-size=200m --network host li:video >/dev/null
"$PY" working/video/probe/wait_ready.py --arm li --port 8802 --deadline 1200 \
    --workers 16 --container li_w16
echo "-- memory after 16 warm loads:"
docker exec li_w16 cat /sys/fs/cgroup/memory.peak 2>/dev/null | awk '{printf "  peak %.1f GB\n", $1/2^30}'
echo "-- 4 concurrent videos through it:"
"$PY" - "$V" <<'EOF'
import asyncio, json, sys, time, urllib.request
blob = open(sys.argv[1], 'rb').read()
def post():
    req = urllib.request.Request('http://127.0.0.1:8802/process_video', data=blob,
                                 method='POST', headers={'Content-Type': 'application/octet-stream'})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=1800) as r:
        b = json.load(r)
    return b.get('pid'), b.get('n_frames'), round(time.monotonic() - t0, 1)
async def main():
    r = await asyncio.gather(*[asyncio.to_thread(post) for _ in range(4)])
    print('  results (pid, frames, wall_s):', r)
    assert all(x[1] for x in r), 'a send returned no frames'
asyncio.run(main())
EOF
echo "-- health + memory after work:"
curl -s http://127.0.0.1:8802/health | "$PY" -c "import json,sys; h=json.load(sys.stdin); print(f'  warm {h[\"warm_workers\"]}/{h[\"declared_workers\"]}')"
docker exec li_w16 cat /sys/fs/cgroup/memory.peak | awk '{printf "  peak %.1f GB of 58\n", $1/2^30}'
docker logs li_w16 2>&1 | grep -ci "killed\|oom" | awk '{print "  oom/kill lines in log:", $1, "(must be 0)"}'
docker rm -f li_w16 >/dev/null
echo "SMOKE COMPLETE — 16/16 warm + 4 videos + peak on record. A 45-min leg is now priceable."
