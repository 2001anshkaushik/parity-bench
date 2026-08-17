#!/usr/bin/env python3
"""Re-verify M6 by methods that share no code with the ones that produced it.

TWO COUNTING ERRORS HAVE ALREADY BEEN FOUND IN THIS METRIC (a slice that ran past end-of-file,
and a layer mapping that put a dependency manifest in `pipeline_definition`). A third would not
be surprising, so nothing here reuses the first pass:

  extraction   METHOD A sliced text from `class X` to the next unindented line.
               METHOD B uses `ast.parse` and the compiler's own `lineno`/`end_lineno`.
  counting     METHOD A used Leela's triple-quote state-machine counter.
               METHOD B uses Python's `tokenize` module, which fails differently: it understands
               single-quoted docstrings, strings that CONTAIN a triple quote, implicit
               continuations and decorators, none of which a state machine sees.

               (Written the other way round, this very docstring failed to parse: an embedded
               triple quote closed it early. That is the bug class, demonstrated on itself.)

Disagreement between A and B is a finding and is printed, not reconciled silently.

AND THE DEEPER PROBLEM. The minimal result reverses on one cell — RocketRide's
`pipeline_definition`, a JSON file whose line count is set by its indentation. The same pipeline
is 1 line compact and 78 at indent 2. A metric whose conclusion flips on whitespace is not
measuring authorship, so this also reports two measures that formatting cannot touch:

  SEMANTIC UNITS    declared pipeline nodes + authored functions/classes/methods
  CANONICAL BYTES   every artifact normalised by its language's own canonicaliser, then bytes

Neither is a substitute for LOC; both are checks on whether LOC's answer is real.
"""
from __future__ import annotations

import ast
import io
import json
import sys
import tokenize
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
LEELA = ROOT.parent / "ref-final" / "leela" / "aws_bench"


# ---------------------------------------------------------------- METHOD B: tokenize counter

def loc_tokenize(src: str) -> int:
    """Non-blank, non-comment, non-docstring lines — decided by Python's own tokenizer.

    A line counts if it carries at least one token that is not a comment, not a docstring, and
    not pure layout (NEWLINE/NL/INDENT/DEDENT/ENDMARKER). Docstrings are identified structurally
    via the AST rather than by "starts with a quote", so a string that merely begins a line is
    still code.
    """
    tree = ast.parse(src)
    doc_lines = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                d = body[0]
                doc_lines.update(range(d.lineno, (d.end_lineno or d.lineno) + 1))
    live = set()
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE,
                        tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER):
            continue
        if not tok.string.strip():
            continue
        for ln in range(tok.start[0], tok.end[0] + 1):
            if ln not in doc_lines:
                live.add(ln)
    return len(live)


def loc_text(path: Path) -> int:
    """Non-Python files (Dockerfile, .pipe): non-blank, non-`#`-comment lines."""
    n = 0
    for line in path.read_text(errors="replace").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            n += 1
    return n


def class_src_ast(path: Path, name: str) -> str:
    """Exact source of one class, by the compiler's own line span. No text scanning."""
    src = path.read_text()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            lines = src.splitlines()
            return "\n".join(lines[node.lineno - 1:node.end_lineno]) + "\n"
    raise KeyError(f"{name} not found in {path}")


# ---------------------------------------------------------------- layer maps

WW = ROOT / "weekend_worker.py"

LAYERS = {
    "as_built": {
        "llamaindex": {
            "pipeline_definition": ["working/ws1/pipeline.py", "working/ws1/schema.py"],
            "compute_transforms": ["working/ws1/service.py"],
            "serving_integration": ["docker/Dockerfile.llamaindex", "working/ws1/run_service.sh"],
            "client_harness": ["@LlamaHttpArm", "@LlamaHttpPdfArm"],
        },
        "rocketride": {
            "pipeline_definition": ["working/pipes/product_pdf.pipe"],
            "compute_transforms": [],
            "serving_integration": ["docker/Dockerfile.rocketride"],
            "client_harness": ["@RocketArm", "@RocketPdfArm"],
        },
    },
    "minimal": {
        "llamaindex": {
            "pipeline_definition": [],
            "compute_transforms": ["working/minimal/li/service.py"],
            "serving_integration": ["working/minimal/li/Dockerfile"],
            "client_harness": ["working/minimal/li/client.py"],
        },
        "rocketride": {
            "pipeline_definition": ["working/minimal/rr/pipeline.pipe"],
            "compute_transforms": [],
            "serving_integration": ["working/minimal/rr/Dockerfile"],
            "client_harness": ["working/minimal/rr/client.py"],
        },
    },
}


def count_b(entry: str) -> int:
    if entry.startswith("@"):
        return loc_tokenize(class_src_ast(WW, entry[1:]))
    p = ROOT / entry
    if p.suffix == ".py":
        return loc_tokenize(p.read_text())
    return loc_text(p)


def measure_b() -> Dict:
    out = {}
    for variant, arms in LAYERS.items():
        out[variant] = {}
        for arm, layers in arms.items():
            per = {L: sum(count_b(f) for f in fs) for L, fs in layers.items()}
            per["arm_total"] = sum(per.values())
            out[variant][arm] = per
    return out


# ---------------------------------------------------------------- method A, for comparison

def measure_a() -> Dict:
    """Leela's counter + the ORIGINAL text slicer, replayed so A and B can be diffed."""
    sys.path.insert(0, str(LEELA))
    try:
        from metrics.m6_loc import count_loc                       # type: ignore
    except Exception:
        return {}
    import tempfile
    tmp = Path(tempfile.mkdtemp())

    def slice_text(name: str) -> Path:
        lines = WW.read_text().splitlines()
        i = next(n for n, l in enumerate(lines) if l.startswith(f"class {name}"))
        j = len(lines)
        for n in range(i + 1, len(lines)):
            l = lines[n]
            if l and not l[0].isspace() and not l.startswith(("#", ")", "]", "}")):
                j = n
                break
        p = tmp / f"{name}.py"
        p.write_text("\n".join(lines[i:j]) + "\n")
        return p

    out = {}
    for variant, arms in LAYERS.items():
        out[variant] = {}
        for arm, layers in arms.items():
            per = {}
            for L, fs in layers.items():
                per[L] = sum(count_loc(slice_text(f[1:]) if f.startswith("@") else ROOT / f)
                             for f in fs)
            per["arm_total"] = sum(per.values())
            out[variant][arm] = per
    return out


# ---------------------------------------------------------------- formatting sensitivity

def pipe_variants(path: Path) -> Dict[str, int]:
    cfg = json.loads(path.read_text())
    return {
        "as_stored": loc_text(path),
        "indent_2": len(json.dumps(cfg, indent=2).splitlines()),
        "one_node_per_line": 2 + len(cfg["components"]),
        "compact": len(json.dumps(cfg, separators=(",", ":")).splitlines()),
    }


# ---------------------------------------------------------------- formatting-independent

def semantic_units() -> Dict:
    """Authorship decisions, not lines.

    DEFENDED: a declared node and an authored function are both "a thing the developer chose to
    add". Neither moves when a formatter runs. This is the closest thing to counting the design
    rather than the transcript.
    LIMIT, stated: it treats one pipeline node as equal to one Python function, and they are not
    equal in effort. It is a floor on authorship, not a measure of labour.
    """
    def py_units(entries: List[str]) -> Tuple[int, Dict[str, int]]:
        total, detail = 0, {}
        for e in entries:
            src = class_src_ast(WW, e[1:]) if e.startswith("@") else (ROOT / e).read_text()
            tree = ast.parse(src)
            n = sum(1 for x in ast.walk(tree)
                    if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
            detail[e] = n
            total += n
        return total, detail

    out = {}
    for variant, arms in LAYERS.items():
        out[variant] = {}
        for arm, layers in arms.items():
            py = [f for L, fs in layers.items() for f in fs
                  if f.startswith("@") or f.endswith(".py")]
            n_py, detail = py_units(py)
            pipes = [f for L, fs in layers.items() for f in fs if f.endswith(".pipe")]
            n_nodes = sum(len(json.loads((ROOT / f).read_text())["components"]) for f in pipes)
            out[variant][arm] = {"authored_python_units": n_py, "declared_nodes": n_nodes,
                                 "total": n_py + n_nodes, "detail": detail}
    return out


def canonical_bytes() -> Dict:
    """Every artifact through its own language's canonicaliser, then bytes.

    DEFENDED: `ast.unparse(ast.parse(src))` is Python's own normal form — it discards comments,
    docstrings survive as string literals, and every formatting choice is erased. JSON gets
    `sort_keys` + tight separators, its canonical form. Both sides are then compared as bytes of
    normalised content, which whitespace cannot move.
    LIMIT, stated: bytes reward terse identifiers and punish descriptive ones, and the Dockerfile
    canonicaliser below is hand-rolled because no standard one exists.
    """
    def canon(entry: str) -> int:
        if entry.startswith("@"):
            return len(ast.unparse(ast.parse(class_src_ast(WW, entry[1:]))).encode())
        p = ROOT / entry
        if p.suffix == ".py":
            return len(ast.unparse(ast.parse(p.read_text())).encode())
        if p.suffix == ".pipe":
            return len(json.dumps(json.loads(p.read_text()), sort_keys=True,
                                  separators=(",", ":")).encode())
        # Dockerfile / shell: unwrap `\` continuations, drop comments, collapse whitespace runs.
        text = p.read_text().replace("\\\n", " ")
        keep = [" ".join(l.split()) for l in text.splitlines()
                if l.strip() and not l.strip().startswith("#")]
        return len("\n".join(keep).encode())

    out = {}
    for variant, arms in LAYERS.items():
        out[variant] = {}
        for arm, layers in arms.items():
            out[variant][arm] = sum(canon(f) for fs in layers.values() for f in fs)
    return out


# ---------------------------------------------------------------- report

def main() -> int:
    b, a = measure_b(), measure_a()

    print("=" * 74)
    print("1. INDEPENDENT RE-VERIFICATION  (B: ast spans + tokenize)")
    print("=" * 74)
    print(f"{'variant':<10}{'arm':<12}{'layer':<22}{'A':>5}{'B':>5}  agree")
    disagreements = []
    for variant in ("as_built", "minimal"):
        for arm in ("llamaindex", "rocketride"):
            for L in ("pipeline_definition", "compute_transforms", "serving_integration",
                      "client_harness", "arm_total"):
                va, vb = (a.get(variant, {}).get(arm, {}).get(L), b[variant][arm][L])
                ok = va == vb
                if not ok:
                    disagreements.append((variant, arm, L, va, vb))
                print(f"{variant:<10}{arm:<12}{L:<22}{va if va is not None else '-':>5}{vb:>5}"
                      f"  {'yes' if ok else 'NO  <<<'}")
    print()
    if disagreements:
        print(f"!! {len(disagreements)} DISAGREEMENT(S) between methods:")
        for v, arm, L, va, vb in disagreements:
            print(f"   {v}/{arm}/{L}: A={va} B={vb}")
    else:
        print("Both methods agree on every cell. The previous numbers reproduce.")

    lm = b["minimal"]["llamaindex"]["arm_total"]
    rm = b["minimal"]["rocketride"]["arm_total"]
    lb = b["as_built"]["llamaindex"]["arm_total"]
    rb = b["as_built"]["rocketride"]["arm_total"]

    print("\n" + "=" * 74)
    print("2. THE CELL THAT DECIDES IT — minimal ratio at each formatting")
    print("=" * 74)
    pv = pipe_variants(ROOT / "working/minimal/rr/pipeline.pipe")
    stored = pv["as_stored"]
    print(f"LlamaIndex minimal total = {lm} (contains no JSON; unaffected)\n")
    print(f"{'pipe formatting':<22}{'pipe LOC':>9}{'RR total':>10}{'LI/RR':>9}   conclusion")
    for k in ("as_stored", "indent_2", "one_node_per_line", "compact"):
        rr = rm - stored + pv[k]
        ratio = lm / rr
        verdict = ("RocketRide LARGER" if ratio < 1 else
                   "RocketRide smaller" if ratio < 2 else "RocketRide much smaller")
        print(f"{k:<22}{pv[k]:>9}{rr:>10}{ratio:>9.2f}   {verdict}")
    print("\nOne file's indentation moves the answer across the 1.0x line. That is the finding.")

    print("\n" + "=" * 74)
    print("3. FORMATTING-INDEPENDENT MEASURES")
    print("=" * 74)
    su, cb = semantic_units(), canonical_bytes()
    print(f"{'measure':<26}{'LI built':>10}{'RR built':>10}{'LI min':>9}{'RR min':>9}{'min ratio':>11}")
    print(f"{'semantic units':<26}"
          f"{su['as_built']['llamaindex']['total']:>10}{su['as_built']['rocketride']['total']:>10}"
          f"{su['minimal']['llamaindex']['total']:>9}{su['minimal']['rocketride']['total']:>9}"
          f"{su['minimal']['llamaindex']['total'] / max(su['minimal']['rocketride']['total'], 1):>11.2f}")
    print(f"{'canonical bytes':<26}"
          f"{cb['as_built']['llamaindex']:>10}{cb['as_built']['rocketride']:>10}"
          f"{cb['minimal']['llamaindex']:>9}{cb['minimal']['rocketride']:>9}"
          f"{cb['minimal']['llamaindex'] / max(cb['minimal']['rocketride'], 1):>11.2f}")
    print(f"{'LOC (as stored)':<26}{lb:>10}{rb:>10}{lm:>9}{rm:>9}"
          f"{lm / max(rm, 1):>11.2f}")

    out = {"method_b": b, "method_a": a, "disagreements": disagreements,
           "pipe_formatting": pv, "semantic_units": su, "canonical_bytes": cb,
           "minimal_ratio_by_formatting": {
               k: round(lm / (rm - stored + pv[k]), 3) for k in pv}}
    (Path(__file__).resolve().parent / "verify_report.json").write_text(json.dumps(out, indent=1))
    print("\nwritten -> working/minimal/verify_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
