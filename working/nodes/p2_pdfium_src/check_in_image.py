"""Run by the ENGINE's own Python inside rr:p2-pdfium (build check, no measurement). HARD GATE (P2
pre-registration G_build_C): pypdfium2 AND its top-level pypdfium2_cfg module import (P1's image lacked
pypdfium2_cfg), one corpus PDF parses to more than zero characters the H6 way, and both prototype node
files carry the right variant flag (read from their source with ast: importing a node outside the engine
runtime fails on rocketlib's own dependencies, which the engine puts on its path at run time — found on the
box 2026-09-24; the node's load inside the engine is proven by the first leg's counters, gate G_node_C). Any failure exits non-zero with the reason; success prints one
P2_PDFIUM_CHECK line whose "ok" is true."""
import json
import sys

out = {"python": sys.version.split()[0], "ok": False}
try:
    import pypdfium2_cfg  # noqa: F401  — the module P1's copy left out
    out["pypdfium2_cfg"] = getattr(pypdfium2_cfg, "__file__", None)
    import pypdfium2 as pdfium
    out["pypdfium2"] = __import__("importlib.metadata").metadata.version("pypdfium2")
    pdf = pdfium.PdfDocument(sys.argv[1])
    parts = []
    for i in range(len(pdf)):
        pg = pdf[i]; tp = pg.get_textpage(); parts.append(tp.get_text_range()); tp.close(); pg.close()
    pdf.close()
    out["pages"], out["chars"] = len(parts), len("\n".join(parts))
    if out["chars"] <= 0:
        raise RuntimeError(f"parsed {sys.argv[1]} to zero characters")
    import ast
    for m, want in (("pdfium_pure", False), ("pdfium_hybrid", True)):
        src = open(f"/opt/rocketride/engine/nodes/{m}/IInstance.py", encoding="utf-8").read()  # the engine's Python defaults to ASCII (register 57)
        flags = {t.id: ast.literal_eval(n.value) for n in ast.parse(src).body if isinstance(n, ast.Assign)
                 for t in n.targets if isinstance(t, ast.Name) and t.id in ("HYBRID", "STUB")}
        out[m] = flags
        if flags.get("HYBRID") is not want or flags.get("STUB", "absent") is not None:
            raise RuntimeError(f"{m}: {flags}, want HYBRID={want} STUB=None")
        for f in ("__init__.py", "IGlobal.py", "services.json"):
            open(f"/opt/rocketride/engine/nodes/{m}/{f}").close()
    out["ok"] = True
except Exception as e:  # noqa: BLE001 — the reason is the gate's evidence
    out["error"] = f"{type(e).__name__}: {e}"
print("P2_PDFIUM_CHECK " + json.dumps(out))
sys.exit(0 if out["ok"] else 1)
