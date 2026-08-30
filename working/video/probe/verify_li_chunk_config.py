#!/usr/bin/env python3
"""RULING L in-container verification — runs INSIDE the li:video image:

    docker run --rm --network none \
      -v <repo>/working/video/probe/verify_li_chunk_config.py:/tmp/verify_li_chunk_config.py:ro \
      --entrypoint python li:video /tmp/verify_li_chunk_config.py

(run_ruling_l_box.sh issues exactly that). Three proofs, each crossing the
entry-2 independence boundary (execution), because entry 1 is the register's
standing warning that a chunk config can be accepted and silently discarded
downstream of everything traced — the engine's own kwargs-filter did exactly
that:

  1. PARSE — the image env reached this process and li_video.service parsed
     it: WS1V_CHUNK_OVERLAP is PRESENT and service.CHUNK_OVERLAP == 0 (plus
     4000/chars). Presence is asserted, not just the parsed value — an
     absent var would coast on the code default and leave the image-env
     layer unproven.
  2. REALIZATION — the pipeline built exactly as the service lifespan builds
     it (constants from the service module's one env parse; the splitter
     constructed by pipeline.warm(), the one real copy) splits films-regime
     text (short unique newline-joined lines) with ZERO seam retention: no
     chunk's head repeats the previous chunk's tail.
  3. NULL CONTROL — a SentenceSplitter at overlap=200 on the SAME text must
     show seam retention, or the seam detector cannot detect the thing it
     checks for and the whole verification is VOID. (The control tests the
     INSTRUMENT; only the subject goes through the service's construction.)

Exit 0 all three hold / 1 any fails. JSON verdict on stdout either way.
"""
import json
import os
import sys


def seam_overlap(prev: str, nxt: str, cap: int = 600) -> int:
    """Longest L <= cap with nxt[:L] == prev[-L:] — retained-overlap chars."""
    for length in range(min(len(prev), len(nxt), cap), 0, -1):
        if nxt[:length] == prev[-length:]:
            return length
    return 0


def films_regime_text(n_lines: int = 300) -> str:
    """Short, unique, newline-joined per-frame-JSON-shaped lines (~120-150
    chars): the films regime. Uniqueness makes seam repetition unambiguous."""
    lines = []
    for i in range(n_lines):
        det = [{'label': f'obj{i % 7}',
                'score': round(0.31 + (i % 60) / 100, 2),
                'box': {'x1': float(i), 'y1': float(i % 97),
                        'x2': float(i + 40), 'y2': float(i % 89 + 30)}}]
        lines.append(json.dumps({'frame': i, 'detections': det}))
    return '\n'.join(lines)


def main() -> int:
    verdict = {'probe': 'verify_li_chunk_config', 'ruling': 'L (4000/0/chars)'}
    fails = []

    # 1. PARSE
    raw = {k: os.environ.get(k) for k in
           ('WS1V_CHUNK_SIZE', 'WS1V_CHUNK_OVERLAP', 'WS1V_SPLIT_UNIT')}
    verdict['env_raw'] = raw
    if raw['WS1V_CHUNK_OVERLAP'] is None:
        fails.append('WS1V_CHUNK_OVERLAP ABSENT from the environment — the '
                     'image-env layer is unproven (the code default would '
                     'mask its absence)')
    from li_video import service as svc
    parsed = {'chunk_size': svc.CHUNK_SIZE, 'chunk_overlap': svc.CHUNK_OVERLAP,
              'split_unit': svc.SPLIT_UNIT}
    verdict['parsed'] = parsed
    if parsed != {'chunk_size': 4000, 'chunk_overlap': 0,
                  'split_unit': 'chars'}:
        fails.append(f'service parsed {parsed}, not 4000/0/chars')

    from importlib.metadata import version
    verdict['llama_index_core'] = version('llama-index-core')

    # 2. REALIZATION — the service's own construction (service.py lifespan
    # kwargs, values from the module's one parse; warm() builds the splitter).
    from li_video.pipeline import LlamaIndexVideoPipeline
    text = films_regime_text()
    p = LlamaIndexVideoPipeline(
        embed_model_name=svc.EMBED_MODEL, interval_s=svc.INTERVAL_S,
        threshold=svc.THRESHOLD, chunk_size=svc.CHUNK_SIZE,
        chunk_overlap=svc.CHUNK_OVERLAP, split_unit=svc.SPLIT_UNIT,
        device=svc.DEVICE)
    p.warm()
    chunks = p._splitter.split_text(text)
    seams = [seam_overlap(a, b) for a, b in zip(chunks, chunks[1:])]
    verdict['subject'] = {'n_chunks': len(chunks),
                          'chunk_chars': [len(c) for c in chunks],
                          'seam_overlaps': seams,
                          'sum_chunk_chars': sum(len(c) for c in chunks),
                          'source_chars': len(text)}
    if len(chunks) < 4:
        fails.append(f'subject split produced only {len(chunks)} chunks — '
                     'the seam check would be vacuous')
    if seams and max(seams) >= 20:
        fails.append(f'REALIZED OVERLAP AT CONFIG 0: max seam {max(seams)} '
                     f'chars (seams {seams}) — the configured overlap did '
                     'not reach the splitter, or SentenceSplitter ignores it')

    # 3. NULL CONTROL — instrument test: overlap=200 must be VISIBLE.
    from llama_index.core.node_parser import SentenceSplitter
    ctrl = SentenceSplitter(chunk_size=4000, chunk_overlap=200,
                            tokenizer=lambda t: t)
    cchunks = ctrl.split_text(text)
    cseams = [seam_overlap(a, b) for a, b in zip(cchunks, cchunks[1:])]
    verdict['null_control_200'] = {'n_chunks': len(cchunks),
                                   'seam_overlaps': cseams}
    if len(cchunks) < 4:
        fails.append(f'null control produced only {len(cchunks)} chunks')
    if not cseams or max(cseams) < 50:
        fails.append('NULL CONTROL DID NOT FIRE: overlap=200 shows max seam '
                     f'{max(cseams) if cseams else 0} < 50 chars — the seam '
                     'detector cannot detect retention; verification VOID')

    verdict['fails'] = fails or None
    verdict['PASS'] = not fails
    print(json.dumps(verdict, indent=1))
    print('RULING L VERIFY:',
          'PASS — 4000/0/chars parsed AND realized; null control fired'
          if not fails else f'FAIL — {fails}')
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
