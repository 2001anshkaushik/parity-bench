#!/usr/bin/env python3
"""Generate SAMPLE exports for team review — the SHAPE is real, the numbers are
synthetic. Every field is produced by the same driver functions the real run
uses (leg_gates, steady_window, cross_gates, provenance_leela.build), so what
the team approves here is byte-shaped like what the box will emit. Synthetic
values are plausible (durations from the real manifest spread, 4000/200
chunking, ~10 detections/frame) and the file says SAMPLE loudly at the top.

Regenerate with:  python3 working/video/samples/make_sample_export.py
"""

import hashlib
import json
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'working'))
sys.path.insert(0, str(ROOT / 'working' / 'video'))

import driver_video as dv                      # noqa: E402
from harness import provenance_leela as pvl    # noqa: E402

random.seed(2026)
OUT_DIR = Path(__file__).parent
NS = 1_000_000_000

# Realistic corpus slice: durations across the measured 6x spread.
VIDEOS = [('ES2002a.Corner.avi', 1248.3), ('ES2002b.Corner.avi', 2266.1),
          ('ES2002c.Corner.avi', 2388.4), ('ES2005a.Corner.avi', 470.6),
          ('ES2014d.Corner.avi', 2905.4), ('ES2006b.Corner.avi', 1815.0),
          ('ES2007c.Corner.avi', 1400.5), ('ES2008a.Corner.avi', 990.2),
          ('ES2009d.Corner.avi', 2600.8), ('ES2010b.Corner.avi', 1150.9)]


def synth_record(i, name, dur, t0_ns, concurrency=4):
    frames = dv.expected_frames({'video_s': dur, 'fps': 25.0}, 15)
    det_pf = [random.randint(4, 15) for _ in range(frames)]
    chars = sum(d * 185 + 4 for d in det_pf)
    n_chunks = max(1, -(-chars // 3800))
    chunk_chars = [random.randint(3400, 4000) for _ in range(n_chunks - 1)] + [chars % 3800 or 1200]
    hashes = [hashlib.sha256(f'{name}:{i}:{k}'.encode()).hexdigest() for k in range(n_chunks)]
    admit = t0_ns + (i // concurrency) * 60 * NS + (i % concurrency) * NS
    wall = dur / 6.5  # ~6.5x realtime at the working point — synthetic
    return {
        'video': name, 'role': 'measured',
        'submitted_sha256': hashlib.sha256(name.encode()).hexdigest(),
        'bytes': int(dur * 40_000),
        'expected_frames': frames, 'video_s_manifest': dur,
        'enqueue_ns': t0_ns, 'admit_ns': admit,
        'done_ns': admit + int(wall * NS), 'wall_s': round(wall, 2),
        'n_chunks': n_chunks, 'chunk_chars': chunk_chars, 'chunk_sha256': hashes,
        'sum_chunk_chars': sum(chunk_chars),
        'frames_observed': frames, 'frames_observed_naive_upper_bound': frames + 5,
        'frames_observed_method': 'bracket-count-overlap-stripped',
        'frames_observed_rawdecode': frames, 'frame_count_methods_agree': True,
        'frame_label_multisets': [sorted(random.sample(
            ['person', 'chair', 'laptop', 'cup', 'tv', 'dining table'], k=min(d, 6)))
            for d in det_pf],
        'frame_scores': [[round(random.uniform(0.3, 0.99), 6) for _ in range(d)] for d in det_pf],
        'chunkid_monotone': True, 'whole_list_doubled': False,
        'n_detections': sum(det_pf), 'detections_per_frame': det_pf,
        'embed_dim': 384,
        'embedding_norms': [round(1.0 + random.uniform(-4e-4, 4e-4), 6) for _ in range(n_chunks)],
        'stage_s': None, 'serving_pid': None, 'token_index': i % 4,
    }


def main():
    t0 = 1_000_000 * NS
    rows = [{'file': n, 'video_s': d, 'fps': 25.0, 'role': 'measured'} for n, d in VIDEOS]
    records = [synth_record(i, n, d, t0) for i, (n, d) in enumerate(VIDEOS)]
    # make one duplication-trigger-eligible record show the gate armed side
    # (>=64 chunks happens organically on long meetings)
    long_rec = records[4]          # ES2014d, 48 min
    assert long_rec['n_chunks'] >= 64, long_rec['n_chunks']
    # determinism repeat record (sequential legs emit one)
    rep = dict(records[0])
    rep['video'] = records[0]['video'] + '::repeat'
    rep['role'] = 'determinism_repeat'
    all_records = records + [rep]

    gates = dv.leg_gates(all_records, rows, 'rocketride_video', 15,
                         liveness_min_fraction=0.90)
    gates['dropped_frame_attribution'] = {
        'channel_alive': True, 'attribution': 'no drop warnings',
        'liveness_marker': '[entrypoint] RocketRide engine',
        'drop_warnings': None, 'n_drop_warnings': 0}
    window = dv.steady_window(records, 4)
    ok_frames = sum(r['frames_observed'] for r in records)
    ok_video_s = sum(r['video_s_manifest'] for r in records)
    leg_wall = (max(r['done_ns'] for r in records) - min(r['admit_ns'] for r in records)) / NS
    lens = [c for r in records for c in r['chunk_chars']]
    prov = pvl.build(
        arm='rocketride_video', mode='blast', corpus_sha='SAMPLE' + '0' * 58,
        corpus_n=len(records), offered_concurrency=4, configured_concurrency=4,
        warmup_policy='driver-side, 16 disjoint manifest warm rows, coverage proven per instance',
        timeout_s=7200, parser='ffmpeg fps=1/15 + rfdetr(RF-DETR base, thr 0.3)',
        chunk_size=max(lens), chunk_overlap=0, embedding_model=dv.EMBED_MODEL,
        container='rr', splitter='RecursiveCharacterTextSplitter')

    export = {
        '_SAMPLE': 'SYNTHETIC NUMBERS, REAL SHAPE — generated by make_sample_export.py '
                   'through the same driver functions the box uses. For team review of '
                   'the data flow only; no value here is a measurement.',
        'arm': 'rocketride_video', 'posture': 'parity[tokens=4,threads=1]', 'leg': 'blast',
        'submission_order': ('manifest-seq: deterministic by meeting id, identical both '
                             'arms; NOT longest-first — sorting to shorten the drain tail '
                             'would benchmark our scheduler, not the frameworks '
                             '(ruling 2026-08-20)'),
        'throughput': {
            'total_span_s': round(leg_wall, 1),
            'total_frames': ok_frames,
            'total_frames_per_s': round(ok_frames / leg_wall, 3),
            'total_realtime_factor': round(ok_video_s / leg_wall, 2),
            'steady_window': window,
        },
        'n_offered': len(records), 'n_records': len(all_records), 'n_errors': 0,
        'leg_wall_s': round(leg_wall, 1), 'aborted_by_breaker': False,
        'wall_s_order_stats': sorted(round(r['wall_s'], 1) for r in records),
        'latency_normalized': {
            'wall_s_per_video_minute': sorted(
                round(r['wall_s'] / (r['video_s_manifest'] / 60), 2) for r in records),
            'note': 'raw per-video wall_s and video_s_manifest are in every record; '
                    'this normalization keeps the 6x duration confound visible',
            'p50': None, 'max': None, 'n': len(records),
            'percentile_policy': 'p50/max/n only below n=50 (no dressed percentiles)',
        },
        'preleg_load1': 1.42,
        'preleg_container_idle_cores': {'rr': 1.002},
        'preleg_foreign_excess': 0.42,
        'quiet_box_override': None,
        'driver_cpu': {'cpu_s': 41.2, 'share_of_box': 0.0021, 'over_1pct': False},
        'gates': gates,
        'provenance_leela': prov,
        'provenance_video': {
            'pipe_sha256': 'SAMPLE' + '0' * 58,
            'manifest_sha256': 'SAMPLE' + '0' * 58,
            'posture': {'name': 'parity', 'tokens': 4, 'threads_config': 1,
                        'threads_note': 'explicit use(threads=)'},
            'identity_readback': {
                'rr': {'rfdetr_import_ok': True,
                       'versions': {'rfdetr': '<from constraints.txt>', 'torch': '<pinned>',
                                    'transformers': '4.53.3'}}},
            'thread_pin_parity': {'PASS': True, 'readers': ['li_worker_101', 'rr_task'],
                                  'disagreements': None,
                                  'values_agreed': {'OMP_NUM_THREADS': '1',
                                                    'torch_num_threads': 1}},
            'interval_s': 15,
            'frames_observed_method': 'bracket-count-overlap-stripped',
            'chunk_config_source': 'measured from records (config literal never exported)',
        },
    }
    # fill the p50/max the driver derives at export time
    ln = export['latency_normalized']['wall_s_per_video_minute']
    export['latency_normalized']['p50'] = ln[len(ln) // 2]
    export['latency_normalized']['max'] = ln[-1]

    (OUT_DIR / 'sample_export_blast.json').write_text(json.dumps(export, indent=1))

    # cross-arm sample: reuse the real cross_gates over two synthetic jsonl files
    with tempfile.TemporaryDirectory() as td:
        li_records = []
        for r in records:
            li = dict(r)
            li['sum_chunk_chars'] = int(r['sum_chunk_chars'] * random.uniform(0.995, 1.005))
            li['n_chunks'] = r['n_chunks'] + random.choice([-1, 0, 1])
            li['serving_pid'] = 100 + (records.index(r) % 4)
            li_records.append(li)
        rrp, lip = Path(td) / 'rr.jsonl', Path(td) / 'li.jsonl'
        rrp.write_text('\n'.join(json.dumps(r) for r in records) + '\n')
        lip.write_text('\n'.join(json.dumps(r) for r in li_records) + '\n')
        cross = dv.cross_gates(rrp, lip, 0.02, gate3_armed='probe_20260821TXXXXXX')
    cross['_SAMPLE'] = 'SYNTHETIC — shape review only'
    (OUT_DIR / 'sample_cross_gates.json').write_text(json.dumps(cross, indent=1))
    print(f'wrote {OUT_DIR}/sample_export_blast.json '
          f'({len(json.dumps(export)) // 1024} KB) and sample_cross_gates.json')
    print(f"gate verdicts in sample: "
          f"{ {k: (v.get('PASS') if isinstance(v, dict) else v) for k, v in gates.items()} }")


if __name__ == '__main__':
    main()
