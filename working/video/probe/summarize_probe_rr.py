#!/usr/bin/env python3
"""Flatten probe_rr_t*.json into the RR thread curve — and print the two
probe-measured inputs the Crossroad-23 manifest re-cut requires.

Exists because the first attempt to read the curve queried keys that do not
exist in probe_rr's schema (total_s / send1_s / cpu_cores / peak_anon_mb) and
got None for everything — which read as "the runs produced nothing" while the
same files were simultaneously PASSING gate-3 staging. The real schema:

    report.sends[i].label                      'first-load' | 'steady-state'
    report.sends[i].wall_s                     per-send wall seconds
    report.sends[i].documents.n_chunks         chunks in the response
    report.sends[i].documents.total_chars      chars entering the splitter
    report.sends[i].documents.frames_from_chunks / frames_rawdecode
    report.sends[i].cgroup.cpu_s               container CPU-seconds this send
    report.sends[i].cgroup.cpu_util_of_32      cores-of-32 utilisation
    report.sends[i].cgroup.memory_peak_bytes / anon_bytes_after

Run from the probe dir (box):  ~/.venv-floor/bin/python summarize_probe_rr.py
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path


def main() -> int:
    files = sorted(glob.glob(str(Path(sys.argv[1] if len(sys.argv) > 1 else '.')
                                 / 'probe_rr_t*.json')))
    if not files:
        print('NOT DONE — no probe_rr_t*.json here (pass the directory as arg 1)')
        return 1
    tot_frames = tot_dets = tot_chars = 0
    for f in files:
        r = json.load(open(f))
        print(f'\n== {Path(f).name}  (tokens={r.get("tokens")}, rc={r.get("rc")})')
        for s in r.get('sends', []):
            d = s.get('documents') or {}
            cg = s.get('cgroup') or {}
            mult = d.get('frame_label_multisets') or []
            dets = sum(len(m) for m in mult)
            print(f"  {s.get('label', '?'):12} wall_s={s.get('wall_s')} "
                  f"n_chunks={d.get('n_chunks')} total_chars={d.get('total_chars')} "
                  f"frames={d.get('frames_from_chunks')}/{d.get('frames_rawdecode')} "
                  f"(bracket/rawdecode) dets={dets} "
                  f"cpu_s={cg.get('cpu_s')} cores_of_32={cg.get('cpu_util_of_32')} "
                  f"peak_mb={round((cg.get('memory_peak_bytes') or 0) / 1048576)} "
                  f"anon_mb={round((cg.get('anon_bytes_after') or 0) / 1048576)} "
                  f"doubled={d.get('whole_list_doubled')}")
            if s.get('label') == 'steady-state' and d.get('frames_rawdecode'):
                tot_frames += d['frames_rawdecode']
                tot_dets += dets
                tot_chars += d.get('total_chars') or 0
    if tot_frames and tot_dets:
        print('\n== Crossroad-23 re-cut inputs (steady-state sends, probe-measured) ==')
        print(f'  --measured-dpf {tot_dets / tot_frames:.2f}   '
              f'(detections/frame over {tot_frames} frames)')
        print(f'  --measured-chars-per-det {tot_chars / tot_dets:.1f}   '
              f'(chars entering the splitter / detection)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
