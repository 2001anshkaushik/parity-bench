#!/usr/bin/env python3
"""Generate the P1-C node directories from the template.
    gen.py <out_nodes_dir> [--stubs]   -> <out>/pdfium_pure, <out>/pdfium_hybrid (+ test stubs)"""
import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
out = Path(sys.argv[1])
variants = [("pdfium_pure", False, None), ("pdfium_hybrid", True, None)]
if "--stubs" in sys.argv:
    variants += [("pdfium_stubtext", True, "text"), ("pdfium_stubempty", True, "empty")]
tmpl = (SRC / "IInstance.tmpl.py").read_text()
for name, hybrid, stub in variants:
    d = out / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "IInstance.py").write_text(tmpl.replace("__HYBRID__", repr(hybrid)).replace("__STUB__", repr(stub)))
    (d / "IGlobal.py").write_text("from rocketlib import IGlobalBase\n\n\nclass IGlobal(IGlobalBase):\n    pass\n")
    (d / "__init__.py").write_text("from .IGlobal import IGlobal\nfrom .IInstance import IInstance\n\n__all__ = ['IGlobal', 'IInstance']\n")
    lanes = {"tags": ["text", "tags"]} if hybrid else {"tags": ["text"]}
    svc = {"title": f"P1 {name}", "protocol": f"{name}://", "classType": ["data"], "capabilities": [],
           "register": "filter", "node": "python", "path": f"nodes.{name}", "prefix": name.title().replace("_", ""),
           "description": ["Benchmark-only P1-C prototype (NOT part of RocketRide; safe to delete): pypdfium2 text extraction"
                           + (" with the Tika parse node as fallback on empty text or error." if hybrid else " only.")],
           "lanes": lanes, "shape": [{"section": "Pipe", "title": f"P1 {name}", "properties": []}]}
    (d / "services.json").write_text(json.dumps(svc, indent=1) + "\n")
    print(f"generated {d} (hybrid={hybrid}, stub={stub})")
