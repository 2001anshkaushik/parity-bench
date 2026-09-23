#!/usr/bin/env python3
"""P0 H6: one Python PDF parser as a line-protocol worker (the Python twin of TikaBatch.java).

    p0_parse_worker.py <pypdf|pypdfium2> <out_dir>

Prints {"ready": true, ...}, then reads one absolute PDF path per line on stdin and answers one
JSON line per path: wall_s and cpu_s of the parse call alone (the file is read into memory first,
as the LlamaIndex service receives the body in memory), and the exception if one was raised. The
text is written as UTF-8 to <out_dir>/<name>.txt so every parser is measured by one reader. A
document that hangs is the orchestrator's to time out: it kills this process and starts another.

Extraction calls, stated so the comparison is reproducible:
  pypdf      pypdf.PdfReader(BytesIO(data)); "\\n".join(page.extract_text() or "" for page in
             reader.pages) — exactly working/ws1/pipeline.py:extract, the LlamaIndex arm's call
  pypdfium2  PdfDocument(data); per page get_textpage().get_text_range(), joined with "\\n"
             (PDFium, C++; Apache-2.0 / BSD-3-Clause)
"""
from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path


def parse_pypdf(data: bytes) -> str:
    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def parse_pypdfium2(data: bytes) -> str:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(data)
    try:
        parts = []
        for i in range(len(pdf)):
            page = pdf[i]
            tp = page.get_textpage()
            parts.append(tp.get_text_range())
            tp.close()
            page.close()
        return "\n".join(parts)
    finally:
        pdf.close()


PARSERS = {"pypdf": parse_pypdf, "pypdfium2": parse_pypdfium2}


def version(parser: str) -> str:
    if parser == "pypdf":
        import pypdf
        return pypdf.__version__
    from importlib.metadata import version as _v       # pypdfium2 5.x dropped V_PYPDFIUM2
    import pypdfium2
    return f"{_v('pypdfium2')} (pdfium {getattr(pypdfium2, 'PDFIUM_INFO', '?')})"


def main() -> int:
    parser, out_dir = sys.argv[1], Path(sys.argv[2])
    fn = PARSERS[parser]
    out_dir.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"ready": True, "parser": parser, "version": version(parser)}), flush=True)
    for line in sys.stdin:
        path = line.strip()
        if not path:
            continue
        p = Path(path)
        data = p.read_bytes()
        err, text = None, ""
        c0, t0 = time.process_time(), time.perf_counter()
        try:
            text = fn(data)
        except BaseException as e:                     # noqa: BLE001 — every failure is data
            err = f"{type(e).__name__}: {e}"[:500]
        t1, c1 = time.perf_counter(), time.process_time()
        if err is None:
            (out_dir / f"{p.name}.txt").write_text(text, encoding="utf-8", errors="surrogatepass")
        rec = {"doc": p.name, "wall_s": t1 - t0, "cpu_s": c1 - c0}
        if err:
            rec["error"] = err
        print(json.dumps(rec), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
