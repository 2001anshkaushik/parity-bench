"""Run by the ENGINE's own Python inside rr:p1-pdfium (build check, no measurement): pypdfium2 imports,
reports its version, parses one corpus PDF the H6 way, and both prototype node modules import."""
import json, sys
out = {"python": sys.version.split()[0]}
import pypdfium2 as pdfium
out["pypdfium2"] = getattr(pdfium, "V_PYPDFIUM2", None) or __import__("importlib.metadata").metadata.version("pypdfium2")
pdf = pdfium.PdfDocument(sys.argv[1])
parts = []
for i in range(len(pdf)):
    pg = pdf[i]; tp = pg.get_textpage(); parts.append(tp.get_text_range()); tp.close(); pg.close()
pdf.close()
out["pages"], out["chars"] = len(parts), len("\n".join(parts))
sys.path.insert(0, "/opt/rocketride/engine")
for m in ("nodes.pdfium_pure", "nodes.pdfium_hybrid"):
    mod = __import__(m, fromlist=["IInstance"])
    out[m] = {"HYBRID": sys.modules[m + ".IInstance"].HYBRID, "STUB": sys.modules[m + ".IInstance"].STUB}
print("P1_PDFIUM_CHECK " + json.dumps(out))
