# =============================================================================
# P2-C PROTOTYPE PARSE NODE (benchmark-only; NOT part of RocketRide; safe to delete).
# Generated from working/nodes/p2_pdfium_src/IInstance.tmpl.py by working/nodes/p2_pdfium_src/gen.py —
# edit the template, never the generated copies.
#
# Consumes the raw document on the `tags` lane (the parse node's input) and extracts text with
# pypdfium2 (PDFium: Apache-2.0 / BSD-3-Clause), page by page, joined with newlines — the H6 call.
#   PURE    (HYBRID = False): the text, or nothing if it is empty or PDFium raises.
#   HYBRID  (HYBRID = True):  the text if it is non-empty; otherwise the document's buffered tags
#           are replayed, byte for byte, on this node's `tags` output to the pipeline's Tika parse
#           node (P1-B's fixed wrapper), which then extracts the text.
# P2 (from P1's template): the counters are written after EVERY document, with the last error, so a
# short leg (the eleven + 25 warm-up) is readable and a PDFium that raises is visible (P1's failure).
# PDFium is not thread-safe: one process-wide lock serialises every PDFium call (ctypes releases
# the GIL inside them, so Python stages keep running). One engine process, one pipeline, no pool.
# =============================================================================
import threading

from rocketlib import IInstanceBase

HYBRID = __HYBRID__
STUB = __STUB__            # laptop wiring tests only: None | 'text' | 'empty'
_LOCK = threading.Lock()
_STATS_LOCK = threading.Lock()
_STATS = {'docs': 0, 'text': 0, 'fallback': 0, 'errors': 0, 'last_error': None}


def _extract(data: bytes) -> str:
    if STUB == 'text':
        return 'P1 PDFIUM WIRING TEST TEXT ' * 8
    if STUB == 'empty':
        return ''
    import pypdfium2 as pdfium
    with _LOCK:
        pdf = pdfium.PdfDocument(data)
        try:
            parts = []
            for i in range(len(pdf)):
                page = pdf[i]
                tp = page.get_textpage()
                parts.append(tp.get_text_range())
                tp.close()
                page.close()
            return '\n'.join(parts)
        finally:
            pdf.close()


class IInstance(IInstanceBase):
    def open(self, obj):
        self._buf = bytearray()
        self._tags = []
        self._fallback = False

    def writeTag(self, tag):
        if self._fallback:
            return                      # after a replay, the rest of the object's tags flow on to Tika
        tid = str(tag.tagId)
        raw = bytes(tag.asBytes)
        if HYBRID:
            self._tags.append(raw)
        if tid.endswith('SDAT'):
            hs = len(raw) - tag.size
            self._buf += raw[hs:] if hs > 0 else b''
        elif tid.endswith('SEND'):
            self._finish()              # a fallback replays every buffered tag, SEND included, so
                                        # SEND's own default forward is suppressed either way
        return self.preventDefault()

    def _finish(self):
        text, err = '', None
        try:
            text = _extract(bytes(self._buf))
        except Exception as e:           # noqa: BLE001 — a PDFium failure is an empty result
            err = f'{type(e).__name__}: {e}'
        with _STATS_LOCK:                # executor threads finish documents concurrently
            _STATS['docs'] += 1
            if err:
                _STATS['errors'] += 1
                _STATS['last_error'] = err[:300]
            if text.strip():
                _STATS['text'] += 1
            elif HYBRID:
                _STATS['fallback'] += 1
        if text.strip():
            self.instance.writeText(text)
        elif HYBRID:
            self._fallback = True
            for raw in self._tags:
                self.instance.writeTag(raw)
        self._buf = bytearray()
        self._tags = []
        _write_stats()

    def close(self):
        self._buf = bytearray()
        self._tags = []


def _write_stats():
    # called from executor threads: a private lock and an atomic replace, so a reader never sees half a file
    try:
        import json
        import os
        path = os.environ.get('P1_PDFIUM_STATS', f"/tmp/p1_pdfium_{'hybrid' if HYBRID else 'pure'}.json")
        with _STATS_LOCK:
            with open(path + '.tmp', 'w') as f:
                json.dump({'hybrid': HYBRID, **_STATS}, f)
            os.replace(path + '.tmp', path)
    except Exception:                    # noqa: BLE001
        pass
