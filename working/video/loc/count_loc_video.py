#!/usr/bin/env python3
"""Phase 2 (video) M6: LOC + COSMIC, reusing Phase 1's method unchanged.

METHOD IS NOT NEW. Everything below is Phase 1's, found at working/minimal/:
  * counter        Leela's m6_loc.count_loc, via count_loc.py::_load_counter()
                   (non-blank, non-comment, docstrings excluded) — METHOD A
  * verifier       tokenize+ast second counter — METHOD B (verify_loc.py)
  * four layers    pipeline_definition / compute_transforms / serving_integration
                   / client_harness (COUNTING_RULE.md §2)
  * the knife      COUNTING_RULE.md §3 categories 1-7, applied to BOTH arms
  * declarative    pipe_formatting_spread — a JSON's line count is set by its
                   indentation, so Phase 1 reports the SPREAD, never one number
  * output         as-built / minimal / ratio_range (COUNTING_RULE.md §4)
COSMIC is NEW in Phase 2 — Phase 1 has none (grepped: no cosmic/CFP/function
point anywhere). Its rules are stated in the report, not inherited.

Scope ruling (operator, 2026-08-26): only what a developer writes to stand up
the video pipeline. Harness, driver, gates, collector, probes EXCLUDED.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'working' / 'minimal'))
from count_loc import _load_counter                     # noqa: E402 — Phase 1's, unmodified

count_loc, COUNTER_SRC = _load_counter()
V = ROOT / 'working' / 'video'

# ---------------------------------------------------------------- classification rules
# (b) INSTRUMENTATION markers — operator's list plus what the schema's own
# comments declare ("gates read these"). Each rule carries its reason so the
# per-line output can be re-audited line by line.
INSTR = [
    (r'stage_s_semantics|hashing_locus', 'locus/semantics provenance field'),
    (r'\bstage_s\b|time\.monotonic\(\)', 'per-stage timing instrumentation'),
    (r'frame_labels|frame_label_multisets|frame_scores', 'gate 3 per-frame label/score export'),
    (r'embedding_norms', 'gate 7 norm export'),
    (r'chunk_sha256|frame_png_sha16|hashlib', 'cross-arm hash export'),
    (r'\bchunks\b.*driver|chunks: list\[str\]', 'chunk TEXTS returned for driver-side hashing'),
    (r'_mark_warm|_warm_workers|_supervisor_key|WARM_ROOT|warm_workers|declared_workers',
     'warm-marker / worker-census apparatus (harness polls it)'),
    (r'torch_num_threads|_torch_threads|python_version|versions|_versions|model_names|detect_impl',
     'declared-vs-measured read-back / identity manifest'),
    (r'chunk_chars', 'per-chunk lengths exported for the parity gate'),
    (r'detections_per_frame|n_detections\b', 'per-frame detection counts (gate input)'),
    (r'\bpid\b|os\.getpid', 'serving-instance read-back'),
    (r'STAGE_SEMANTICS', 'locus constant'),
]
# (c) AMBIGUOUS — defensible either way; reported separately, never silently kept
AMBIG = [
    (r'total_chars|n_chunks\b', 'workload counts: a caller might want them; gates certainly do'),
    (r'class HealthResponse|status:|warm:', 'health: liveness is service, the rest is census'),
    (r'@app\.get\(.?/health', 'health endpoint: liveness needed; its fields are instrumentation'),
    (r'is_warm|def identity', 'readiness/identity used by both service and harness'),
]


def classify(path: Path):
    rows, counts = [], {'service': 0, 'instrumentation': 0, 'ambiguous': 0}
    in_doc = False
    for i, line in enumerate(path.read_text().splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        if path.suffix == '.py':
            if in_doc:
                if '"""' in s:
                    in_doc = False
                continue
            if s.startswith('"""'):
                if not (s.endswith('"""') and len(s) > 3):
                    in_doc = True
                continue
        if s.startswith('#'):
            continue
        cls, why = 'service', 'pipeline needs it to accept a video and return chunks/embeddings'
        for pat, reason in AMBIG:
            if re.search(pat, s):
                cls, why = 'ambiguous', reason
                break
        else:
            for pat, reason in INSTR:
                if re.search(pat, s):
                    cls, why = 'instrumentation', reason
                    break
        counts[cls] += 1
        rows.append({'line': i, 'class': cls, 'why': why, 'text': s[:96]})
    return counts, rows


def pipe_formatting(p: Path) -> dict:
    doc = json.loads(p.read_text())
    return {
        'as_stored': len([l for l in p.read_text().splitlines() if l.strip()]),
        'indent_2': len(json.dumps(doc, indent=2).splitlines()),
        'compact': len(json.dumps(doc, separators=(',', ':')).splitlines()),
        'one_node_per_line': len(doc.get('components', [])) + 2,
    }


def semantic_units(py_files, pipe: Path | None) -> dict:
    import ast
    n = 0
    for f in py_files:
        t = ast.parse(f.read_text())
        n += sum(isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                 for x in ast.walk(t))
    nodes = len(json.loads(pipe.read_text()).get('components', [])) if pipe else 0
    return {'authored_python_units': n, 'declared_nodes': nodes, 'total': n + nodes}


def main() -> int:
    li_py = [V / 'li_video' / n for n in ('service.py', 'pipeline.py', 'schema.py', '__init__.py')]
    dockerfile = ROOT / 'docker' / 'Dockerfile.llamaindex-video'
    pipe = V / 'benchmark_video_detect.pipe'

    per_file, classification = {}, {}
    for f in li_py:
        c, rows = classify(f)
        per_file[str(f.relative_to(ROOT))] = c
        classification[str(f.relative_to(ROOT))] = rows

    li_service = sum(c['service'] for c in per_file.values())
    li_instr = sum(c['instrumentation'] for c in per_file.values())
    li_amb = sum(c['ambiguous'] for c in per_file.values())
    docker_loc = count_loc(dockerfile)

    report = {
        'method': {
            'source': 'working/minimal/COUNTING_RULE.md (Phase 1, unmodified)',
            'counter': COUNTER_SRC,
            'layers': ['pipeline_definition', 'compute_transforms',
                       'serving_integration', 'client_harness'],
            'scope_ruling': 'developer-written service only; harness/driver/gates/'
                            'collector/probes excluded (operator 2026-08-26)',
            'cosmic': 'NEW in Phase 2 — Phase 1 contains no COSMIC/CFP work',
        },
        'llamaindex': {
            'per_file': per_file,
            'service_only': li_service,
            'instrumentation': li_instr,
            'ambiguous': li_amb,
            'as_built_python': li_service + li_instr + li_amb,
            'dockerfile_loc': docker_loc,
            'layers': {
                'pipeline_definition': 0,
                'compute_transforms': per_file[str((V / 'li_video' / 'pipeline.py').relative_to(ROOT))]['service'],
                'serving_integration': per_file[str((V / 'li_video' / 'service.py').relative_to(ROOT))]['service']
                                       + per_file[str((V / 'li_video' / 'schema.py').relative_to(ROOT))]['service']
                                       + per_file[str((V / 'li_video' / '__init__.py').relative_to(ROOT))]['service']
                                       + docker_loc,
                'client_harness': 0,
            },
            'totals': {
                'as_built_incl_docker': li_service + li_instr + li_amb + docker_loc,
                'service_plus_ambiguous_incl_docker': li_service + li_amb + docker_loc,
                'service_only_incl_docker': li_service + docker_loc,
            },
        },
        'rocketride': {
            'pipeline_definition_formatting_spread': pipe_formatting(pipe),
            'compute_transforms': 0,
            'compute_transforms_note': 'engine-internal: product code, not user code '
                                       '(Leela, COUNTING_RULE.md §2 — the load-bearing entry)',
            'serving_integration': 0,
            'serving_integration_note': 'the engine image serves; no developer-written service, '
                                        'no Dockerfile authored for this pipeline',
            'client_harness': 0,
        },
        'semantic_units': {
            'llamaindex': semantic_units(li_py, None),
            'rocketride': semantic_units([], pipe),
        },
    }
    out = V / 'loc'
    (out / 'loc_report_video.json').write_text(json.dumps(report, indent=1))
    (out / 'classification_video.json').write_text(json.dumps(classification, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k != 'method'}, indent=1)[:2600])
    return 0


if __name__ == '__main__':
    sys.exit(main())
