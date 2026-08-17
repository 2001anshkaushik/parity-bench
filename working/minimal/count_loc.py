#!/usr/bin/env python3
"""M6 lines of code: as-built and minimal, both arms, one counter.

The counter is Leela's `m6_loc.count_loc` at `a5c3b5d`, IMPORTED where his clone is available and
otherwise reproduced byte-for-byte below with a recorded provenance flag. It is never modified: a
locally-tweaked counter would make our numbers incomparable with his, which is the one thing this
metric exists to avoid.

Read `COUNTING_RULE.md` before the numbers. The rule is the finding.

CORRECTION carried here (see COUNTING_RULE.md §5): the 2026-08-16 client_harness figures were
wrong. The slicer ran each arm class from its `class` line to the next `class` line, and
`LlamaHttpPdfArm` is the LAST class in weekend_worker.py, so its slice ran to end-of-file and
swept in ~130 unrelated lines. Both arms also omitted their base classes, where the connect,
token and transport code lives. Both are fixed here.

    python3 working/minimal/count_loc.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent.parent
LEELA = ROOT.parent / "reference-now" / "leela" / "aws_bench"


def _load_counter():
    """Leela's counter, imported if his clone is on disk, else reproduced verbatim."""
    if (LEELA / "metrics" / "m6_loc.py").exists():
        sys.path.insert(0, str(LEELA))
        from metrics.m6_loc import count_loc                      # type: ignore
        return count_loc, f"imported from {LEELA}/metrics/m6_loc.py"

    def count_loc(path: Path) -> int:                             # verbatim copy
        prefix = {".py": "#", ".sh": "#", "Dockerfile": "#"}.get(path.suffix or path.name)
        n = 0
        in_docstring = False
        for line in path.read_text(errors="replace").splitlines():
            s = line.strip()
            if not s:
                continue
            if path.suffix == ".py":
                if in_docstring:
                    if '"""' in s:
                        in_docstring = False
                    continue
                if s.startswith('"""'):
                    if not (s.endswith('"""') and len(s) > 3):
                        in_docstring = True
                    continue
            if prefix and s.startswith(prefix):
                continue
            n += 1
        return n
    return count_loc, "reproduced verbatim (Leela clone not present at reference-now/leela)"


count_loc, COUNTER_SOURCE = _load_counter()


def class_slice(src_file: Path, name: str, out: Path) -> Path:
    """Extract ONE class body to a temp file so the counter sees only that class.

    Ends at the next top-level `class`/assignment, NOT merely the next `class` — the bug that
    produced the wrong 2026-08-16 figure was a slice that ran off the end of the file because the
    target happened to be the last class in it.
    """
    lines = src_file.read_text().splitlines()
    i = next(n for n, l in enumerate(lines) if l.startswith(f"class {name}"))
    j = len(lines)
    for n in range(i + 1, len(lines)):
        l = lines[n]
        if l and not l[0].isspace() and not l.startswith(("#", ")", "]", "}")):
            j = n
            break
    out.write_text("\n".join(lines[i:j]) + "\n")
    return out


WW = ROOT / "weekend_worker.py"

AS_BUILT: Dict[str, Dict[str, List[str]]] = {
    "llamaindex": {
        "pipeline_definition": ["working/ws1/pipeline.py", "working/ws1/schema.py"],
        "compute_transforms": ["working/ws1/service.py"],
        "serving_integration": ["docker/Dockerfile.llamaindex", "working/ws1/run_service.sh"],
        "client_harness": ["@LlamaHttpArm", "@LlamaHttpPdfArm"],
    },
    "rocketride": {
        "pipeline_definition": ["working/pipes/product_pdf.pipe"],
        "compute_transforms": [],          # engine-internal: product code, not user code
        "serving_integration": ["docker/Dockerfile.rocketride"],
        "client_harness": ["@RocketArm", "@RocketPdfArm"],
    },
}

MINIMAL: Dict[str, Dict[str, List[str]]] = {
    "llamaindex": {
        # No declarative artifact exists on this arm: the stage wiring IS the handler, and it is
        # counted once, under compute_transforms. requirements.txt is counted on NEITHER arm —
        # Leela counts no dependency manifest for LangGraph or for RocketRide, and adding one for
        # us alone would be an asymmetric rule.
        "pipeline_definition": [],
        "compute_transforms": ["working/minimal/li/service.py"],
        "serving_integration": ["working/minimal/li/Dockerfile"],
        "client_harness": ["working/minimal/li/client.py"],
    },
    "rocketride": {
        "pipeline_definition": ["working/minimal/rr/pipeline.pipe"],
        "compute_transforms": [],          # engine-internal: product code, not user code
        "serving_integration": ["working/minimal/rr/Dockerfile"],
        "client_harness": ["working/minimal/rr/client.py"],
    },
}


def measure(layers: Dict[str, Dict[str, List[str]]], tmp: Path) -> Dict:
    rep: Dict = {}
    for arm, ls in layers.items():
        arm_out, total = {}, 0
        for layer, files in ls.items():
            per = {}
            for f in files:
                if f.startswith("@"):
                    p = class_slice(WW, f[1:], tmp / f"{f[1:]}.py")
                else:
                    p = ROOT / f
                per[f] = count_loc(p) if p.exists() else "MISSING"
            n = sum(v for v in per.values() if isinstance(v, int))
            arm_out[layer] = {"total": n, "files": per}
            total += n
        arm_out["arm_total"] = total
        rep[arm] = arm_out
    return rep


def pipe_formatting_spread() -> Dict:
    """How much of the RocketRide `pipeline_definition` figure is JSON formatting?

    This is the weakest number in the whole metric and it must not ship as a bare integer. A
    `.pipe` is data, and its line count depends entirely on how the writer indented it — a
    repo-local format-on-save daemon rewrote ours mid-edit while this was being counted. Python
    line counts do not have this property, so the RocketRide arm is the only one exposed to it.
    Reported as a spread over three defensible serialisations of the SAME pipeline.
    """
    out = {}
    for label, path in (("as_built", ROOT / "working/pipes/product_pdf.pipe"),
                        ("minimal", ROOT / "working/minimal/rr/pipeline.pipe")):
        cfg = json.loads(path.read_text())
        variants = {
            "as_stored": len([l for l in path.read_text().splitlines() if l.strip()]),
            "indent_2": len(json.dumps(cfg, indent=2).splitlines()),
            "compact": len(json.dumps(cfg, separators=(",", ":")).splitlines()),
            "one_node_per_line": 2 + len(cfg["components"]),
        }
        out[label] = variants
    return out


def main() -> int:
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    ab, mn = measure(AS_BUILT, tmp), measure(MINIMAL, tmp)
    for p in tmp.glob("*.py"):
        p.unlink()

    print(f"counter: {COUNTER_SOURCE}\n")
    print(f"{'layer':<22}{'LI built':>10}{'LI min':>9}{'RR built':>10}{'RR min':>9}")
    print("-" * 60)
    for layer in ("pipeline_definition", "compute_transforms", "serving_integration",
                  "client_harness"):
        print(f"{layer:<22}{ab['llamaindex'][layer]['total']:>10}"
              f"{mn['llamaindex'][layer]['total']:>9}"
              f"{ab['rocketride'][layer]['total']:>10}"
              f"{mn['rocketride'][layer]['total']:>9}")
    print("-" * 60)
    lb, lm = ab["llamaindex"]["arm_total"], mn["llamaindex"]["arm_total"]
    rb, rm = ab["rocketride"]["arm_total"], mn["rocketride"]["arm_total"]
    print(f"{'ARM TOTAL':<22}{lb:>10}{lm:>9}{rb:>10}{rm:>9}\n")

    # The two extremes of the ratio. LOW pairs the smallest LlamaIndex with the largest
    # RocketRide; HIGH pairs the largest LlamaIndex with the smallest RocketRide. Anything
    # between them is defensible; nothing outside them is.
    lo, hi = lm / rb, lb / rm
    same_knife = lb / rb, lm / rm
    print(f"ratio, minimal/minimal   = {same_knife[1]:.1f}x   (both arms stripped)")
    print(f"ratio, as-built/as-built = {same_knife[0]:.1f}x   (neither arm stripped)")
    print(f"RANGE                    = {lo:.1f}x .. {hi:.1f}x")
    print("\nPUBLISHABLE CLAIM: the range. The two same-knife points sit inside it; the")
    print("endpoints are the mixed pairings and exist to bound a hostile reading.")

    fmt = pipe_formatting_spread()
    print("\nJSON FORMATTING SENSITIVITY — the RocketRide .pipe is the only file in this metric")
    print("whose line count is set by its indentation rather than its content:")
    for label, v in fmt.items():
        print(f"  {label:<9} as_stored={v['as_stored']:>3}  indent_2={v['indent_2']:>3}  "
              f"compact={v['compact']:>3}  one_node_per_line={v['one_node_per_line']:>3}")
    lo_rr = rm - fmt["minimal"]["as_stored"] + fmt["minimal"]["compact"]
    print(f"  -> RR minimal arm_total moves {lo_rr}..{rm} on formatting alone "
          f"({lm / rm:.1f}x..{lm / lo_rr:.1f}x against LI minimal). Quote the spread.")

    out = {"counter_source": COUNTER_SOURCE, "as_built": ab, "minimal": mn,
           "pipe_formatting_spread": fmt,
           "ratio_as_built": round(same_knife[0], 2),
           "ratio_minimal": round(same_knife[1], 2),
           "ratio_range": [round(lo, 2), round(hi, 2)],
           "rule": "working/minimal/COUNTING_RULE.md",
           "removed": "working/minimal/REMOVED.md",
           "validated_by_run": False,
           "validation_note": (
               "counts are static and exact; the MINIMAL implementations are import-checked "
               "only. Functional equivalence needs a box run — see REMOVED.md 'Validation'.")}
    (Path(__file__).resolve().parent / "loc_report.json").write_text(json.dumps(out, indent=1))
    print(f"\nwritten -> working/minimal/loc_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
