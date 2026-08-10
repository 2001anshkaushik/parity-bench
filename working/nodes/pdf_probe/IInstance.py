# Benchmark-only node (NOT part of RocketRide). Safe to delete.
#
# PREMISE UNDER TEST: "RocketRide doesn't allow custom parsing nodes, so Tika is forced."
#
# We already know custom PROCESSING nodes load (split_embed, cpu_probe, noop_probe all run). The
# open question is whether a custom PARSE node can replace the engine's built-in Tika/JNI path.
# This node takes a filesystem path to a PDF on the text lane and extracts with a PYTHON library,
# reporting which library answered and how much text came out.
#
# It reports failure rather than raising, because "the engine refused to load a node that imports
# a third-party PDF library" and "the library is not installed in the engine's interpreter" are
# DIFFERENT findings and must not be collapsed into one traceback.
import os
import sys

from rocketlib import IInstanceBase


class IInstance(IInstanceBase):
    buf: str = ""

    def open(self, obj):
        self.buf = ""

    def writeText(self, text: str):
        self.buf = self.buf + text
        self.preventDefault()

    def closing(self):
        path = self.buf.strip()
        info = {"node": "pdf_probe", "pid": os.getpid(),
                "python": sys.version.split()[0], "path": path}
        lib = None
        try:
            import pypdf
            lib = f"pypdf {pypdf.__version__}"
        except Exception as e:
            info["pypdf_import"] = f"{type(e).__name__}: {e}"
        if lib:
            try:
                import pypdf
                r = pypdf.PdfReader(path)
                txt = "\n".join((pg.extract_text() or "") for pg in r.pages)
                info.update(lib=lib, pages=len(r.pages), chars=len(txt),
                            head=txt[:80].replace("\n", " "))
            except Exception as e:
                info.update(lib=lib, parse_error=f"{type(e).__name__}: {e}")
        import json as _json
        self.instance.writeText("PDFPROBE " + _json.dumps(info))

    def close(self):
        self.buf = ""
