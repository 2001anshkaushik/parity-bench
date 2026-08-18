"""Undefined-name detection: the check that would have caught defect #36 before a 40-minute run.

`py_compile` proves a file PARSES; it says nothing about whether the names it uses exist.
`NameError: LI_CONTAINER` sat in an `if EXTERNAL` branch of the provenance block through every
local run and detonated post-loop on the first external run — after both arms had streamed
9,975 records and before any report was written.

Python's own `symtable` computes real scoping: a name a function loads that is neither local,
free (closure), a module-level assignment/import, nor a builtin is a NameError waiting for its
branch to execute. That is exactly the class of bug a conditional can hide from every test that
does not take the branch.

Honest limits, stated: module-level use-before-def is not caught (module symbols are one flat
scope); names materialised dynamically (setattr/exec) would false-positive (we have none); a
star import makes a file unverifiable and is reported as such rather than skipped.
"""
from __future__ import annotations

import ast
import builtins
import symtable
from pathlib import Path
from typing import Dict, List

_DUNDERS = {"__file__", "__name__", "__doc__", "__package__", "__spec__", "__loader__",
            "__builtins__", "__annotations__", "__cached__", "__debug__"}
_CLASS_SCOPE_EXTRA = {"__module__", "__qualname__", "__dict__", "__class__"}


def undefined_names(path) -> List[Dict]:
    src = Path(path).read_text()
    tree = ast.parse(src, str(path))
    if any(isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names)
           for n in ast.walk(tree)):
        return [{"scope": "<module>", "scope_line": 0, "name": "*",
                 "use_lines": [], "note": "star import — file cannot be verified"}]

    top = symtable.symtable(src, str(path), "exec")
    known = {s.get_name() for s in top.get_symbols() if s.is_assigned() or s.is_imported()}

    def collect_global_writes(tb):
        # `global X` + assignment inside a function defines a module name symtable's top
        # level may not list as assigned.
        for s in tb.get_symbols():
            if s.is_declared_global() and s.is_assigned():
                known.add(s.get_name())
        for ch in tb.get_children():
            collect_global_writes(ch)

    for ch in top.get_children():
        collect_global_writes(ch)
    known |= set(dir(builtins)) | _DUNDERS

    # First-use line numbers, for the report only — symtable knows scopes, not use sites.
    use_lines: Dict[str, List[int]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            use_lines.setdefault(node.id, []).append(node.lineno)

    finds: List[Dict] = []

    def walk(tb):
        extra = _CLASS_SCOPE_EXTRA if tb.get_type() == "class" else set()
        for s in tb.get_symbols():
            if s.is_global() and not s.is_assigned() and s.get_name() not in known | extra:
                finds.append({"scope": tb.get_name(), "scope_line": tb.get_lineno(),
                              "name": s.get_name(),
                              "use_lines": sorted(use_lines.get(s.get_name(), []))[:5]})
        for ch in tb.get_children():
            walk(ch)

    for ch in top.get_children():
        walk(ch)
    return finds


def check_files(paths) -> Dict[str, List[Dict]]:
    """{path: findings} for every file with at least one undefined name."""
    out: Dict[str, List[Dict]] = {}
    for p in paths:
        f = undefined_names(p)
        if f:
            out[str(p)] = f
    return out
